from flask import Flask, request, abort
import os
import requests

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

    prompt = f"""
あなたは西洋占星術の占い師HIDEです。

以下の情報をもとに、
優しく、寄り添うように鑑定してください。

【名前】
{user_data.get("name", "")}

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
恋愛運に大きな転換期が出ていました🔮

ただ、
今回の無料鑑定では、
まだ“表面部分”しか見れていません。

本格鑑定では、

・相手の本音
・今後3ヶ月の流れ
・恋愛成就のタイミング
・あなたが今やるべきこと

まで深く読み解いていきます✨

続きが気になる方はこちら👇

https://coconala.com/services/1761884?ref=profile_top_service

━━━━━━━━━━━
"""

        elif "金" in problem or "仕事" in problem:
            ai_reply += """

━━━━━━━━━━━

今回の鑑定では、
金運に大きな変化の流れが出ていました💰

ただ、
今回の無料鑑定では、
まだ“入口部分”しか見れていません。

本格鑑定では、

・今後の金運の流れ
・収入アップのタイミング
・仕事運の転換期
・あなたに合う成功パターン

まで詳しく読み解いていきます✨

続きが気になる方はこちら👇

https://coconala.com/services/1761884?ref=profile_top_service

━━━━━━━━━━━
"""

        else:
            ai_reply += """

━━━━━━━━━━━

今回の鑑定では、
今後の人生に大きな転換期が出ていました🔮

本格鑑定では、

・今後3ヶ月の流れ
・運気の転換タイミング
・あなたが進むべき方向
・開運アクション

まで詳しく読み解いていきます✨

続きが気になる方はこちら👇

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
        "step": "waiting_name"
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
        "鑑定を始めますので、まずはお名前（ニックネームOK）を教えてください😊"
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
            "step": "waiting_name"
        }

        reply_text = (
            "無料鑑定を開始します🔮\n\n"
            "まずは、お名前（ニックネームOK）を教えてください✨"
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

    if current_step == "waiting_name":
        user_states[user_id]["name"] = user_message
        user_states[user_id]["step"] = "waiting_birth"

        reply_text = (
            f"{user_message}さん、ありがとうございます✨\n\n"
            "より正確に鑑定するため、\n"
            "次に生年月日を教えてください😊\n\n"
            "（例：1995/03/21）"
        )

    elif current_step == "waiting_birth":
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
