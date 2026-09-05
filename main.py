from flask import Flask, request, abort
import os
import requests
import secrets
from datetime import datetime, timezone, timedelta

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    FollowEvent
)

from supabase import create_client


app = Flask(__name__)

LINE_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

COCONALA_DIRECT_URL = (
    "https://coconala.com/services/1761884?ref=profile_top_service"
)

configuration = Configuration(access_token=LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# Supabaseの接続に失敗しても、LINE Bot本体は停止させない
supabase_client = None

if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase_client = create_client(
            SUPABASE_URL,
            SUPABASE_KEY
        )
        print("Supabase client initialized.")
    except Exception as e:
        print(f"Supabase initialization error: {e}")
else:
    print("Supabase environment variables are not configured.")

# 現在の会話状態
user_states = {}


def save_user_progress(user_id, status, display_name=None):
    """
    ユーザーの現在の進捗をSupabaseへ保存する。

    Supabase側でエラーが発生しても例外を外へ出さず、
    LINE Botの鑑定・返信処理を継続する。
    """

    if supabase_client is None:
        print(
            f"Supabase unavailable: "
            f"user_id={user_id}, status={status}"
        )
        return

    try:
        user_data = {
            "line_user_id": user_id,
            "status": status
        }

        if display_name:
            user_data["display_name"] = display_name

        existing_user = (
            supabase_client
            .table("users")
            .select("id")
            .eq("line_user_id", user_id)
            .limit(1)
            .execute()
        )

        if existing_user.data:
            (
                supabase_client
                .table("users")
                .update(user_data)
                .eq("line_user_id", user_id)
                .execute()
            )
        else:
            (
                supabase_client
                .table("users")
                .insert(user_data)
                .execute()
            )

        print(
            f"Supabase progress saved: "
            f"user_id={user_id}, status={status}"
        )

    except Exception as e:
        print(
            f"Supabase progress save error: "
            f"user_id={user_id}, status={status}, error={e}"
        )


def create_coconala_tracking_url(user_id):
    """
    ココナラクリック計測用のランダムトークンを作成し、
    Supabaseのusersテーブルへ保存する。

    計測用URLを作れない場合は、
    購入導線を止めないためココナラ直リンクを返す。
    """

    if supabase_client is None or not SUPABASE_URL:
        print(
            f"Coconala tracking unavailable: "
            f"user_id={user_id}"
        )
        return COCONALA_DIRECT_URL

    try:
        token = secrets.token_urlsafe(24)

        existing_user = (
            supabase_client
            .table("users")
            .select("id")
            .eq("line_user_id", user_id)
            .limit(1)
            .execute()
        )

        tracking_data = {
            "coconala_click_token": token,
            "coconala_clicked_at": None
        }

        if existing_user.data:
            (
                supabase_client
                .table("users")
                .update(tracking_data)
                .eq("line_user_id", user_id)
                .execute()
            )
        else:
            (
                supabase_client
                .table("users")
                .insert({
                    "line_user_id": user_id,
                    "status": "coconala_sent",
                    "coconala_click_token": token,
                    "coconala_clicked_at": None
                })
                .execute()
            )

        tracking_url = (
            f"{SUPABASE_URL.rstrip('/')}"
            f"/functions/v1/coconala-click?t={token}"
        )

        print(
            f"Coconala tracking URL created: "
            f"user_id={user_id}"
        )

        return tracking_url

    except Exception as e:
        print(
            f"Coconala tracking URL error: "
            f"user_id={user_id}, error={e}"
        )

        # 計測に失敗しても販売ページへの導線は止めない
        return COCONALA_DIRECT_URL


def get_ai_reply(user_id, user_data, user_message):
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    problem = user_data.get("problem", "")

    # 日本時間の現在日時を自動取得
    jst = timezone(timedelta(hours=9))
    now = datetime.now(jst)
    current_date = now.strftime("%Y年%m月%d日")

    prompt = f"""
あなたは西洋占星術の占い師HIDEです。

現在の日付は【{current_date}】です。

以下の情報をもとに、
優しく、寄り添うように鑑定してください。

【重要な時間軸ルール】
・現在の日付を必ず基準にしてください。
・今後の運勢や未来について述べる場合は、現在以降の年月だけを扱ってください。
・過去の年や月を、未来の出来事として表現しないでください。
・具体的な年月を出す場合は、現在との前後関係を必ず確認してください。

【生年月日】
{user_data.get("birth", "")}

【相談内容】
{problem}

【理想の未来】
{user_message}
"""

    json_data = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "system",
                "content": prompt
            }
        ]
    }

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=json_data
        )

        result = response.json()
        ai_reply = result["choices"][0]["message"]["content"]

        # AI鑑定に成功した後で、
        # このユーザー専用のココナラ計測URLを作成
        coconala_url = create_coconala_tracking_url(user_id)

        if "恋" in problem:
            ai_reply += f"""

━━━━━━━━━━━

今回の無料鑑定では、
恋愛の大きな流れと、
今のあなたが意識した方がいいことを中心にお伝えしました🔮

でも、ここまで読んで、

「相手は本当はどう思っているんだろう」
「このまま待っていていいのかな」
「自分から動くなら、いつがいいんだろう」

そんなことが気になっていませんか？

恋愛って、
気持ちがあるからこそ、
動くべきか待つべきか分からなくなるものです。

本格鑑定では、

・お相手との今の関係性
・これから3ヶ月〜1年の恋愛の流れ
・関係が動きやすいタイミング
・今、自分から動いた方がいいのか
・今後意識したいこと、避けたい行動

まで、
あなたの今の状況に合わせて
さらに詳しく読み解いていきます✨

「この先どうすればいいのか、
もう少し具体的に知ってから動きたい」

そう感じた方は、
本格鑑定をご覧ください👇

{coconala_url}

━━━━━━━━━━━
"""

        elif "仕事" in problem or "転職" in problem:
            ai_reply += f"""

━━━━━━━━━━━

今回の無料鑑定では、
仕事についての大きな流れと、
今意識した方がいいことを中心にお伝えしました🔮

でも、

「このまま今の仕事を続けていいのか」
「転職した方がいいのか」
「動くとしても、今なのか、まだ待つべきなのか」

そこが一番迷うところではないでしょうか。

仕事は生活にも関わるからこそ、
勢いだけでは決めにくいものです。

本格鑑定では、

・今後3ヶ月〜1年の仕事運
・今の環境で意識した方がいいこと
・転職や環境を変えやすいタイミング
・あなたの強みを活かしやすい働き方
・今動くべき時期と慎重にしたい時期

まで、
あなたの状況に合わせて
さらに詳しく読み解いていきます✨

「後悔しないために、
この先どう動けばいいのか知っておきたい」

そう感じた方は、
本格鑑定をご覧ください👇

{coconala_url}

━━━━━━━━━━━
"""

        elif "金" in problem or "収入" in problem or "お金" in problem:
            ai_reply += f"""

━━━━━━━━━━━

今回の無料鑑定では、
金運の大きな流れと、
今意識した方がいいことを中心にお伝えしました🔮

でも、お金のことって、

「この不安はいつまで続くんだろう」
「これから少しは楽になっていくのかな」
「今の自分は何を変えればいいんだろう」

そんなところまで知りたくなりませんか？

お金の不安は、
ただ運気が良い・悪いだけでは
なかなか消えません。

本格鑑定では、

・今後3ヶ月〜1年の金運の流れ
・収入面が動きやすいタイミング
・仕事とお金の流れの関係
・今から意識したいこと
・今できる具体的な行動

まで、
あなたのご相談に合わせて
さらに詳しく読み解いていきます✨

「少しでも不安を減らすために、
これから何をすればいいのか知っておきたい」

そう感じた方は、
本格鑑定をご覧ください👇

{coconala_url}

━━━━━━━━━━━
"""

        else:
            ai_reply += f"""

━━━━━━━━━━━

今回の無料鑑定では、
今の運勢の大きな流れと、
今意識した方がいいことを中心にお伝えしました🔮

でも、

「結局、自分はこれからどうすればいいんだろう」
「このまま進んで大丈夫なのかな」
「何か変えるなら、どこから変えればいいんだろう」

そんな迷いは、
まだ少し残っているかもしれません。

本格鑑定では、

・今後3ヶ月〜1年の流れ
・運気が動きやすいタイミング
・今抱えている悩みとの向き合い方
・あなたが進みやすい方向
・今からできる具体的な行動

まで、
あなたのご相談内容に合わせて
さらに詳しく読み解いていきます✨

「この先どう動けばいいのか、
もう少し具体的に知っておきたい」

そう感じた方は、
本格鑑定をご覧ください👇

{coconala_url}

━━━━━━━━━━━
"""

        return ai_reply

    except Exception as e:
        print(e)
        return "現在AI返信でエラーが発生しています。"


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"


@handler.add(FollowEvent)
def handle_follow(event):
    user_id = event.source.user_id

    # FollowEventがRenderまで届いているか確認するためのログ
    print(f"FollowEvent received: user_id={user_id}")

    user_states[user_id] = {
        "step": "waiting_birth"
    }

    # 友だち追加後、生年月日入力待ちとして記録
    save_user_progress(
        user_id,
        "waiting_birthdate"
    )

    welcome_message = (
        "ご登録ありがとうございます🔮\n\n"
        "占い師HIDEです😊\n\n"
        "この度は、ご登録いただきありがとうございます。\n\n"
        "これから無料で、あなた専用の西洋占星術鑑定をさせていただきます✨\n\n"
        "鑑定では、\n"
        "🌟 あなたの今の運勢\n"
        "🌟 悩みの原因\n"
        "🌟 より良い未来へ進むためのアドバイス\n\n"
        "を、一人ひとりに合わせてお伝えします。\n\n"
        "鑑定を始めますので、まずは生年月日を教えてください😊\n\n"
        "（例：1995/03/21）"
    )

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[
                    TextMessage(text=welcome_message)
                ]
            )
        )


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    user_message = event.message.text

    print(f"Received message: {repr(user_message)}")

    if user_id not in user_states:
        user_states[user_id] = {
            "step": "completed"
        }

    if user_message == "無料鑑定" or user_message == "無料鑑定希望":
        user_states[user_id] = {
            "step": "waiting_birth"
        }

        # 再鑑定開始。生年月日入力待ちとして更新
        save_user_progress(
            user_id,
            "waiting_birthdate"
        )

        reply_text = (
            "無料鑑定を開始します🔮\n\n"
            "まずは、生年月日を教えてください😊\n\n"
            "（例：1995/03/21）"
        )

        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)

            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[
                        TextMessage(text=reply_text)
                    ]
                )
            )

        return

    current_step = user_states[user_id]["step"]

    if current_step == "waiting_birth":
        user_states[user_id]["birth"] = user_message
        user_states[user_id]["step"] = "waiting_problem"

        # 生年月日入力完了。悩み入力待ちとして更新
        save_user_progress(
            user_id,
            "waiting_problem"
        )

        reply_text = (
            "ありがとうございます😊\n\n"
            "次に、今一番悩んでいることを教えてください✨\n\n"
            "恋愛・仕事・人間関係・金運など、\n"
            "どんなことでも大丈夫です😊"
        )

    elif current_step == "waiting_problem":
        user_states[user_id]["problem"] = user_message
        user_states[user_id]["step"] = "waiting_future"

        # 悩み入力完了。理想の未来入力待ちとして更新
        save_user_progress(
            user_id,
            "waiting_future"
        )

        reply_text = (
            "ありがとうございます✨\n\n"
            "最後に、\n\n"
            "今回の鑑定を通して、どうなりたいですか？🔮\n\n"
            "例えば、\n\n"
            "🌸 お金の不安をなくしたい\n"
            "🌸 恋愛をうまくいかせたい\n"
            "🌸 人間関係を改善したい\n"
            "🌸 仕事を良い方向へ進めたい\n\n"
            "など、あなたの願いを教えてください😊"
        )

    elif current_step == "waiting_future":
        reply_text = get_ai_reply(
            user_id,
            user_states[user_id],
            user_message
        )

        user_states[user_id]["step"] = "completed"

        if reply_text == "現在AI返信でエラーが発生しています。":
            save_user_progress(
                user_id,
                "ai_error"
            )
        else:
            # AI鑑定とココナラ案内の送信が完了
            save_user_progress(
                user_id,
                "coconala_sent"
            )

    else:
        reply_text = (
            "無料鑑定をご希望の場合は、\n"
            "リッチメニューの『無料鑑定』を押してください🔮"
        )

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[
                    TextMessage(text=reply_text)
                ]
            )
        )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))

    app.run(
        host="0.0.0.0",
        port=port
    )
