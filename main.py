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


def save_user_field(user_id, field_name, value):
    """
    生年月日・悩み・理想の未来などの入力内容を
    Supabaseのusersテーブルへ保存する。

    Supabase側でエラーが発生しても、
    LINE Bot本体の返信処理は継続する。
    """

    if supabase_client is None:
        print(
            f"Supabase unavailable: "
            f"user_id={user_id}, field={field_name}"
        )
        return

    try:
        (
            supabase_client
            .table("users")
            .update({
                field_name: value
            })
            .eq("line_user_id", user_id)
            .execute()
        )

        print(
            f"Supabase field saved: "
            f"user_id={user_id}, field={field_name}"
        )

    except Exception as e:
        print(
            f"Supabase field save error: "
            f"user_id={user_id}, field={field_name}, error={e}"
        )


def load_user_state(user_id):
    """
    Renderのメモリにユーザー状態がない場合、
    Supabaseのusersテーブルから会話状態と入力内容を復元する。

    Supabaseから取得できない場合は、従来どおりcompletedとして扱う。
    """

    default_state = {
        "step": "completed"
    }

    if supabase_client is None:
        print(
            f"Supabase unavailable while loading state: "
            f"user_id={user_id}"
        )
        return default_state

    try:
        result = (
            supabase_client
            .table("users")
            .select("status,birthdate,problem,future,survey_response")
            .eq("line_user_id", user_id)
            .limit(1)
            .execute()
        )

        if not result.data:
            print(
                f"Supabase user not found while loading state: "
                f"user_id={user_id}"
            )
            return default_state

        row = result.data[0]
        status = row.get("status")

        status_to_step = {
            "waiting_birthdate": "waiting_birth",
            "waiting_problem": "waiting_problem",
            "waiting_future": "waiting_future",
            "waiting_survey": "waiting_survey",
            "manual": "manual",
            "ai_error": "completed",
            "coconala_sent": "completed",
        }

        state = {
            "step": status_to_step.get(status, "completed")
        }

        if row.get("birthdate"):
            state["birth"] = row["birthdate"]

        if row.get("problem"):
            state["problem"] = row["problem"]

        if row.get("future"):
            state["future"] = row["future"]

        print(
            f"Supabase state loaded: "
            f"user_id={user_id}, status={status}, "
            f"step={state['step']}"
        )

        return state

    except Exception as e:
        print(
            f"Supabase state load error: "
            f"user_id={user_id}, error={e}"
        )
        return default_state


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

    extra_reply_text = None

    if user_id not in user_states:
        # Render再起動・スピンダウン後は、
        # Supabaseから会話状態と入力内容を復元する
        user_states[user_id] = load_user_state(user_id)

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

        # 入力された生年月日をSupabaseへ保存
        save_user_field(
            user_id,
            "birthdate",
            user_message
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

        # 入力された悩みをSupabaseへ保存
        save_user_field(
            user_id,
            "problem",
            user_message
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
        # 入力された理想の未来をSupabaseへ保存
        save_user_field(
            user_id,
            "future",
            user_message
        )

        ai_reply = get_ai_reply(
            user_id,
            user_states[user_id],
            user_message
        )

        if ai_reply == "現在AI返信でエラーが発生しています。":
            user_states[user_id]["step"] = "completed"
            save_user_progress(
                user_id,
                "ai_error"
            )
            reply_text = ai_reply
        else:
            # 無料鑑定後は販売ページへ直接誘導せず、
            # 今後の関係につなぐ案内と3問アンケートを送る
            closing_message = (
                "\n\n━━━━━━━━━━━\n\n"
                "今回の鑑定が、少しでもこれからを考えるきっかけになれば嬉しいです\n\n"
                "今後も、占いの結果だけでなく、今の状況をどう受け止め、"
                "これからどう考えていくかというヒントもお届けしていきます\n\n"
                "そのために、最後に3つだけ教えてください\n\n"
                "今後お届けする内容の参考にさせていただきます\n\n"
                "1分ほどで回答できます\n\n"
                "今から簡単なアンケートをお送りします"
            )

            survey_message = (
                "① 今、一番気になっていることはどれですか？\n\n"
                "1. 仕事・働き方\n"
                "2. お金・これからの生活\n"
                "3. 家族・人間関係\n"
                "4. 恋愛・パートナー\n"
                "5. 将来・これからの生き方\n"
                "6. その他\n\n"
                "② 今の状態に一番近いものはどれですか？\n\n"
                "1. 何をどうすればいいのか分からない\n"
                "2. 選択肢はあるけれど、決められない\n"
                "3. やりたいことはあるけれど、行動に移せない\n"
                "4. 自分の気持ちや考えを一度整理したい\n"
                "5. 特に大きな悩みはない\n\n"
                "③ 今、実際に悩んでいることや迷っていることがあれば、自由に教えてください\n\n"
                "占いについての質問だけでなく、\n"
                "仕事・お金・家族・人間関係・将来など、\n"
                "実生活でのお悩みでも大丈夫です\n\n"
                "【返信例】\n"
                "①1\n"
                "②2\n"
                "③今の仕事をこのまま続けるか、転職するか迷っています"
            )

            reply_text = ai_reply + closing_message
            extra_reply_text = survey_message
            user_states[user_id]["step"] = "waiting_survey"
            save_user_progress(
                user_id,
                "waiting_survey"
            )

    elif current_step == "waiting_survey":
        # 3問分の回答を1通のまま保存
        save_user_field(
            user_id,
            "survey_response",
            user_message
        )

        # アンケート回答後はHIDEの手動対応へ切り替える
        user_states[user_id]["step"] = "manual"
        save_user_progress(
            user_id,
            "manual"
        )

        reply_text = (
            "ご回答ありがとうございます😊\n\n"
            "いただいた内容を確認させていただきます"
        )

    elif current_step == "manual":
        # manual中はBotから自動返信しない
        print(f"Manual mode: no bot reply user_id={user_id}")
        return

    else:
        reply_text = (
            "無料鑑定をご希望の場合は、\n"
            "リッチメニューの『無料鑑定』を押してください🔮"
        )

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        messages = [
            TextMessage(text=reply_text)
        ]

        if extra_reply_text:
            messages.append(
                TextMessage(text=extra_reply_text)
            )

        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=messages
            )
        )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))

    app.run(
        host="0.0.0.0",
        port=port
    )
