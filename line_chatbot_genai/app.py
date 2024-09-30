import json
import os

from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (ApiClient, Configuration, MessagingApi,
                                  ReplyMessageRequest, TextMessage)
from linebot.v3.webhooks import MessageEvent, TextMessageContent


configuration = Configuration(access_token=os.getenv('Channel_access_token'))
handler = WebhookHandler(os.getenv('Channel_secret'))

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text="สวัสดีครับคุณลูกค้า ต้องการให้กระผมช่วยอะไรดีครับในวันนี้")]
            )
        )

def lambda_handler(event, context):
    try: 
        body = event['body']
        signature = event['headers']['x-line-signature']
        handler.handle(body, signature)
        return {
            'statusCode': 200,
            'body': json.dumps('Hello from Lambda!')
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps(str(e))
        }