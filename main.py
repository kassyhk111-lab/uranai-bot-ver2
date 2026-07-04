from flask import Flask, request, abort
import os
from pathlib import Path
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

COCONALA_URL = "https://coconala.com/services/1761884?ref=profile_top_service"


def load_base_prompt():
    prompt_path = Path(__file__).parent / "prompts" / "base_prompt.txt"

    try:
        return prompt_path.read_text(encoding="utf-8")
    except Exception as e:
        print(e)
        return "あなたは西洋占星術の占い師HIDEです。優しく、寄り添うように鑑定してください。"


def get_sales_message(problem):
    if "恋" in problem or "復縁" in problem or "片思い" in problem or "結婚" in problem:
        return f"""
━━━━━━━━━━━

今回の無料鑑定では、
恋愛の大きな流れと、今意識した方が良いことを中心にお伝えしました🔮

本格鑑定では、

・相手の本音
・今後3か月〜1年の流れ
・恋愛成就のタイミング
・今やるべき行動
・避けた方が良い時期

まで、さらに詳しく読み解いていきます✨

もっと深く知りたい方はこちらをご覧ください👇

{COCONALA_URL}

━━━━━━━━━━━
"""

    if "金" in problem or "お金" in problem or "仕事" in problem or "転職" in problem or "収入" in problem:
        return f"""
━━━━━━━━━━━

今回の無料鑑定では、
金運・仕事運の大きな流れと、今意識した方が良いことを中心にお伝えしました💰

本格鑑定では、

・今後の金運の流れ
・収入アップのタイミング
・仕事運の転換期
・あなたに合う成功パターン
・避けた方が良い時期

まで、さらに詳しく読み解いていきます✨

もっと深く知りたい方はこちらをご覧ください👇

{COCONALA_URL}

━━━━━━━━━━━
"""

    if "人間関係" in problem or "家族" in problem or "友人" in problem or "職場" in problem:
        return f"""
━━━━━━━━━━━

今回の無料鑑定では、
人間関係の大きな流れと、今意識した方が良いことを中心にお伝えしました🔮

本格鑑定では、

・相手との関係性の流れ
・距離感の取り方
・今後3か月〜1年の変化
・あなたが無理をしないための行動
・避けた方が良い対応

まで、さらに詳しく読み解いていきます✨

もっと深く知りたい方はこちらをご覧ください👇

{COCONALA_URL}

━━━━━━━━━━━
"""

    return f"""
━━━━━━━━━━━

今回の無料鑑定では、
今の大きな流れと、最初に意識した方が良いことを中心にお伝えしました🔮

本格鑑定では、

・今後3か月〜1年の流れ
・運気が大きく動くタイミング
・相談内容に合わせた具体的な行動
・避けた方が良い時期
・あなた自身も気付いていない強み

まで、さらに詳しく読み解いていきます✨

もっと深く知りたい方はこちらをご覧ください👇

{COCONALA_URL}

━━━━━━━━━━━
"""


def get_ai_reply(user_data, user_message):
    base_prompt = load_base_prompt()
    problem = user_data.get("problem", "")

    user_info = f"""
【相談者情報】

名前：
{user_data.get("name", "")}

生年月日：
{user_data.get("birth", "")}

相談内容：
{problem}

今回の鑑定を通して、どうなりたいか：
{user_message}
"""

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    json_data = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "system",
                "content": base_prompt
            },
            {
                "role": "user",
                "content": user_info
            }
        ],
        "temperature": 0.8
    }

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=json_data,
            timeout=30
        )

        result = response.json()
        ai_reply = result["choices"][0]["message"]["content"]
        ai_reply += get_sales_message(problem)

        return ai_reply

    except Exception as e:
        print(e)
        return "現在AI返信でエラーが発生しています。少し時間を置いて、もう一度お試しください。"


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
    user_states[user_id] = {"step": "waiting_name"}

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
                messages=[TextMessage(text=welcome_message)]
            )
        )


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    user_message = event.message.text.strip()

    if user_id not in user_states:
        user_states[user_id] = {"step": "completed"}

    if user_message == "無料鑑定" or user_message == "無料鑑定希望":
        user_states[user_id] = {"step": "waiting_name"}
        reply_text = (
            "無料鑑定を開始します🔮\n\n"
            "まずは、お名前（ニックネームOK）を教えてください✨"
        )
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=reply_text)]
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
        reply_text = get_ai_reply(user_states[user_id], user_message)
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
                messages=[TextMessage(text=reply_text)]
            )
        )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
