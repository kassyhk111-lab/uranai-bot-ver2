from flask import Flask, request, abort
import os
import requests
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

app = Flask(__name__)

LINE_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

configuration = Configuration(access_token=LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

user_states = {}


def get_ai_reply(user_data, user_message):
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

        if "恋" in problem:
            ai_reply += """

━━━━━━━━━━━

今回の鑑定では、
恋愛の大きな流れと、
今意識した方が良いことを中心にお伝えしました🔮

無料鑑定では大まかな方向性までになりますが、
本格鑑定では、

・相手の本音
・今後3ヶ月〜1年の恋愛の流れ
・恋愛成就のタイミング
・今動くべき時期
・避けた方が良い行動

まで、さらに詳しく読み解いていきます✨

まずはサービス内容を見るだけでも大丈夫です。
あなたに必要かどうか、ゆっくりご判断ください。

https://coconala.com/services/1761884?ref=profile_top_service

━━━━━━━━━━━
"""

        elif "仕事" in problem or "転職" in problem:
            ai_reply += """

━━━━━━━━━━━

今回の鑑定では、
仕事についての大きな流れと、
今意識した方が良いことを中心にお伝えしました🔮

無料鑑定では大まかな方向性までになりますが、
本格鑑定では、

・今の仕事を続けるべきか
・転職や環境を変えるタイミング
・今後3ヶ月〜1年の仕事運
・あなたに合いやすい働き方
・今動くべき時期と避けた方が良い時期

まで、さらに詳しく読み解いていきます✨

まずはサービス内容を見るだけでも大丈夫です。
あなたに必要かどうか、ゆっくりご判断ください。

https://coconala.com/services/1761884?ref=profile_top_service

━━━━━━━━━━━
"""

        elif "金" in problem or "収入" in problem or "お金" in problem:
            ai_reply += """

━━━━━━━━━━━

今回の鑑定では、
金運の大きな流れと、
今意識した方が良いことを中心にお伝えしました🔮

無料鑑定では大まかな方向性までになりますが、
本格鑑定では、

・今後の金運の流れ
・収入面が動きやすいタイミング
・お金について意識した方が良いこと
・今やるべき行動
・避けた方が良い時期

まで、さらに詳しく読み解いていきます✨

まずはサービス内容を見るだけでも大丈夫です。
あなたに必要かどうか、ゆっくりご判断ください。

https://coconala.com/services/1761884?ref=profile_top_service

━━━━━━━━━━━
"""

        else:
            ai_reply += """

━━━━━━━━━━━

今回の鑑定では、
今の運勢の大きな流れと、
今意識した方が良いことを中心にお伝えしました🔮

無料鑑定では大まかな方向性までになりますが、
本格鑑定では、

・今後3ヶ月〜1年の流れ
・運気が動きやすいタイミング
・今意識した方が良いこと
・あなたが進みやすい方向
・今できる具体的な行動

まで、さらに詳しく読み解いていきます✨

まずはサービス内容を見るだけでも大丈夫です。
あなたに必要かどうか、ゆっくりご判断ください。

https://coconala.com/services/1761884?ref=profile_top_service

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

    user_states[user_id] = {
        "step": "waiting_birth"
    }

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

    if user_id not in user_states:
        user_states[user_id] = {
            "step": "completed"
        }

    if user_message == "無料鑑定" or user_message == "無料鑑定希望":
        user_states[user_id] = {
            "step": "waiting_birth"
        }

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

        reply_text = (
            "ありがとうございます😊\n\n"
            "次に、今一番悩んでいることを教えてください✨\n\n"
            "恋愛・仕事・人間関係・金運など、\n"
            "どんなことでも大丈夫です😊"
        )

    elif current_step == "waiting_problem":
        user_states[user_id]["problem"] = user_message
        user_states[user_id]["step"] = "waiting_future"

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
            user_states[user_id],
            user_message
        )

        user_states[user_id]["step"] = "completed"

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
