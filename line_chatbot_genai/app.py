import json
import os

from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (ApiClient, Configuration, MessagingApi,
                                  ReplyMessageRequest, TextMessage, CarouselColumn, ImageCarouselTemplate,
    ImageCarouselColumn, DatetimePickerAction, TemplateMessage)
from linebot.v3.webhooks import MessageEvent, TextMessageContent


configuration = Configuration(access_token=os.getenv('Channel_access_token'))
handler = WebhookHandler(os.getenv('Channel_secret'))

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        image_carousel_template = ImageCarouselTemplate(columns=[
            ImageCarouselColumn(image_url='https://static-jaymart.com/ecom/public/2luzo1Tj5R3IbG9xgNNN00fzGx7.jpg',
                                action=DatetimePickerAction(label='datetime',
                                                            data='datetime_postback',
                                                            mode='datetime')),
            ImageCarouselColumn(image_url='https://static-jaymart.com/ecom/public/2hzMS2Xn4g9FzJwUbICYQdOuvNI.jpg',
                                action=DatetimePickerAction(label='date',
                                                            data='date_postback',
                                                            mode='date'))
        ])
        template_message = TemplateMessage(
            alt_text='ImageCarousel alt text', template=image_carousel_template)
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[template_message]
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
        print(e)
        return {
            'statusCode': 500,
            'body': json.dumps(str(e))
        }