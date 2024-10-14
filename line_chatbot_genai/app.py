import json
import os
import random
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (ApiClient, Configuration, MessagingApi,
                                  ReplyMessageRequest, TextMessage, CarouselColumn, ImageCarouselTemplate,
    ImageCarouselColumn, DatetimePickerAction, TemplateMessage, MessageAction,    FlexBubble,
    FlexImage,
    FlexBox,
    FlexText,
    FlexIcon,
    FlexButton,
    FlexSeparator,
    FlexContainer,
    URIAction,
    FlexMessage,
    FlexCarousel,)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
import json
import boto3
from botocore.exceptions import ClientError
import re
from boto3.dynamodb.conditions import Attr

import random
import string


boto3_session = boto3.session.Session()
configuration = Configuration(access_token=os.getenv('Channel_access_token'))
handler = WebhookHandler(os.getenv('Channel_secret'))
# Initialize the Bedrock client
bedrock_agent_runtime_client = boto3.client('bedrock-agent-runtime', region_name='us-east-1')
bedrock_runtime = boto3.client(
    service_name='bedrock-runtime',
    region_name='us-east-1'
)

# declare model id for calling RetrieveAndGenerate API
region = 'us-east-1'
model_id = "mistral.mistral-large-2402-v1:0"
model_arn = f'arn:aws:bedrock:{region}::foundation-model/{model_id}'
prompt_string = """
You are a chatbot that will focus on product recommendations. Here’s a tailored instruction guide for that purpose:

### 1. Define the Purpose of the Chatbot
   - **Primary Objective**: Assist customers by recommending products, providing reviews, prices, and detailed product information.
   - **Main Functions**:
     - Suggest products based on user input.
     - Display reviews and ratings for products.
     - Show product prices.
     - Provide detailed product information (features, specs, etc.).
     - Compare similar products.

### 2. Scope of Product Recommendations
   - **Types of Products**: Ensure the chatbot covers all categories available in-store (clothing, electronics, accessories, etc.).
   - **Recommendation Basis**:
     - User preferences (e.g., style, budget, features).
     - Trending products or popular items.
     - Specific product queries (e.g., "Show me red dresses under $50").
   - **Detailed Product Info**:
     - Price, available colors/sizes, reviews, ratings.
     - Features and specifications for tech products.
   - **Comparison**:
     - Offer the ability to compare two or more products in terms of price, features, or reviews.

### 3. User Interaction Flow
   - **Greeting**: Welcome the user and offer assistance.
     Example: "Hello! Looking for something special today? Let me help you find the perfect product."
   - **Product Inquiry**: Ask what kind of product the customer is interested in.
     Example: "What are you shopping for today? Let me know the product or category you're interested in."
   - **Recommendation Based on Query**:
     Example: "Here are some great options for laptops under $500. Which one would you like to learn more about?"
   - **Show Reviews & Price**:
     Example: "This product has a 4.5-star rating with over 300 reviews. It's priced at $299. Would you like to see more details?"
   - **Provide Detailed Product Information**:
     Example: "This jacket is available in 3 colors: black, blue, and red. It's made of waterproof material and comes in sizes S-XL."
   - **Comparison (if requested)**:
     Example: "Here's a side-by-side comparison of these two laptops: Laptop A has a better battery life, while Laptop B is lighter and cheaper."

### 4. Basic Instructions for Chatbot Behavior
   - **Tone**: Friendly, informative, and focused on assisting with product decisions.
   - **Response Time**: Instant responses to user queries with clear, concise answers.
   - **Interaction Flow**:
     - Ask users their preferences (e.g., price range, color, type of product).
     - Provide relevant product information, avoiding overly technical terms unless necessary.
   - **Error Handling**: If the chatbot doesn’t understand the query:
     Example: "I'm sorry, I couldn't find any products matching that description. Could you try refining your search?"

### 5. Sample Chatbot Script
**Greeting**:
   - "Hi, welcome to our store! How can I assist you with your product search today?"
**Product Discovery**:
   - "What kind of product are you looking for? You can tell me a category or a specific product."
**Product Recommendation**:
   - "Here are some top-rated shoes in your size and budget. Would you like to see reviews or more details?"
**Product Details**:
   - "This smartwatch has a 4.7-star rating, priced at $199. It has features like GPS, heart-rate monitoring, and a 2-day battery life."
**Comparison (if requested)**:
   - "Here's a side-by-side comparison of these two smartphones: Smartphone A has a better camera, while Smartphone B has more storage."
**Please answer only products which contained in our store.**
                
Here are the search results in numbered order:
$search_results$
                
Here is the user's question:
<question>
$query$
</question>
                
$output_format_instructions$

Assistant
"""

prompt_product_id_search = "You are a specialized model. The only task is to identify product names in text and provide their corresponding product IDs. Your task is to process input text, which may contain mentions of various products, and output structured information about the identified products.\n\n**Input**\nYou will receive text that may contain one or more product names. This text can be in any format, including natural language descriptions, lists, or technical specifications.\n\n**Process**\n- Scan the input text for product names from our database.\n- For each identified product name, look up its corresponding product ID in the database.\n- If a product is mentioned but not found in the database, mark it as \"Not found in database\".\n\n**Output**\nFor each product identified in the input, provide the following information:\n**Product Name**: The exact name of the product as mentioned in the input\n**Product ID**: The corresponding ID from the database, or \"Not found in database\" if not present\n\nFormat your output as follows:\n```Product Name: \"[Product Name]\", Product ID: \"[Product ID]\"```\n\nIf multiple products are identified, list each on a new line.\n\nIf no products are identified in the input, output:\n```\"No product names identified in the input.\"```\n                \nHere are the search results in numbered order:\n$search_results$\n                \nHere is the user's question:\n<question>\n$query$\n</question>\n                \n$output_format_instructions$\n\nAssistant"

dynamodb = boto3.resource('dynamodb')

# Select your DynamoDB table
table = dynamodb.Table('product_detail')
table_feature = dynamodb.Table('product_feature')

def generate_random_string(length):
    # Characters allowed in the pattern: [0-9a-zA-Z._:-]
    allowed_characters = string.ascii_letters + string.digits + '._:-'
    
    # Randomly select characters from the allowed set and join them into a string
    random_string = ''.join(random.choice(allowed_characters) for _ in range(length))
    
    return random_string

def get_product_detail(table, product_list):
    """ Function to scan a DynamoDB table where pid in product_list """
    # Define the filter expression for 'status' being either 'active' or 'inactive'
    filter_expression = Attr('pid').is_in(product_list)

    response = table.scan(
        FilterExpression=filter_expression
    )
    data = response.get('Items', [])

    # Continue scanning if there are more items (pagination)
    while 'LastEvaluatedKey' in response:
        response = table.scan(
            FilterExpression=filter_expression,
            ExclusiveStartKey=response['LastEvaluatedKey']
        )
        data.extend(response.get('Items', []))
    
    return data


def retrieve_and_generate(input, knowledge_base_id, model_arn, prompt, sessionId):
    print(input, knowledge_base_id, model_arn, sessionId)
    if sessionId != '':
        response = bedrock_agent_runtime_client.retrieve_and_generate(
            input={
                'text': input
            },
            retrieveAndGenerateConfiguration={
                'type': 'KNOWLEDGE_BASE',
                'knowledgeBaseConfiguration': {
                "retrievalConfiguration": { "vectorSearchConfiguration": { "numberOfResults" :5 } },
                'generationConfiguration': {
                    'promptTemplate': {
                        'textPromptTemplate': prompt
                        }
                },
                'knowledgeBaseId': knowledge_base_id,
                'modelArn': model_arn
                }
            },
            sessionId=sessionId
        )
    else:
        response = bedrock_agent_runtime_client.retrieve_and_generate(
            input={
                'text': input
            },
            retrieveAndGenerateConfiguration={
                'type': 'KNOWLEDGE_BASE',
                'knowledgeBaseConfiguration': {
                "retrievalConfiguration": { "vectorSearchConfiguration": { "numberOfResults" :5 } },
                'generationConfiguration': {
                    'promptTemplate': {
                        'textPromptTemplate': prompt
                        }
                },
                'knowledgeBaseId': knowledge_base_id,
                'modelArn': model_arn
                }
            }
        )
    print(response)
    return response
    

def extract_product_id(input_text):
    # Define the regex pattern (non-capturing groups used)
    pattern = r'\b(\d{13}|\d{16})\b'

    # Find all matches in the input string
    matches = re.findall(pattern, input_text)

    # Convert the matches to integers
    extracted_numbers = [int(match) for match in matches]

    # Print the list of extracted numbers as integers
    print("Extracted numbers as integers:", extracted_numbers)
    return extracted_numbers

def gen_flex_product_list(data):
    output_list = []
    for product in data:
        bubble = FlexBubble(
            direction='ltr',
            hero=FlexImage(
                url=str(product["image"]),
                size='full',
                aspect_ratio='1:1',
                position='relative',
                aspect_mode='cover',
                action=MessageAction(label='Review', text='ขอรีวิวของมือถือรุ่น ' + product["product_name"] )
            ),
            body=FlexBox(
                layout='vertical',
                contents=[
                    # title
                    FlexText(text=str(product["product_name"]), weight='bold', size='md'),
                    # info
                    FlexBox(
                        layout='vertical',
                        margin='lg',
                        spacing='sm',
                        contents=[
                            FlexBox(
                                layout='baseline',
                                spacing='sm',
                                contents=[
                                    FlexText(
                                        text='Price',
                                        color='#aaaaaa',
                                        size='sm',
                                        flex=1
                                    ),
                                    FlexText(
                                        text='฿'+str(int(product["price"])),
                                        wrap=True,
                                        color='#666666',
                                        size='sm',
                                        flex=5
                                    )
                                ],
                            ),
                        ],
                    )
                ],
            ),
            footer=FlexBox(
                layout='vertical',
                spacing='sm',
                contents=[
                    # callAction
                    FlexButton(
                        style='link',
                        height='sm',
                        action=URIAction(label='ซื้อเลย', uri=str(product["url"])),
                    ),
                    # separator
                    FlexSeparator(),
                    # websiteAction
                    FlexButton(
                        style='link',
                        height='sm',
                        action=URIAction(label='ร้านใกล้คุณ', uri="https://www.google.com/maps/dir//4,+Jaymart+%E0%B9%80%E0%B8%8B%E0%B9%87%E0%B8%99%E0%B8%97%E0%B8%A3%E0%B8%B1%E0%B8%A5+%E0%B9%80%E0%B8%A7%E0%B8%B4%E0%B8%A5%E0%B8%94%E0%B9%8C+%E0%B8%8A%E0%B8%B1%E0%B9%89%E0%B8%99+4+4,4%2F1,4%2F2+4+%E0%B8%96.+%E0%B8%A3%E0%B8%B2%E0%B8%8A%E0%B8%94%E0%B8%B3%E0%B8%A3%E0%B8%B4+%E0%B9%80%E0%B8%82%E0%B8%95%E0%B8%9B%E0%B8%97%E0%B8%B8%E0%B8%A1%E0%B8%A7%E0%B8%B1%E0%B8%99+%E0%B8%81%E0%B8%A3%E0%B8%B8%E0%B8%87%E0%B9%80%E0%B8%97%E0%B8%9E%E0%B8%A1%E0%B8%AB%E0%B8%B2%E0%B8%99%E0%B8%84%E0%B8%A3+10330/data=!4m6!4m5!1m1!4e2!1m2!1m1!1s0x30e29ecfde432025:0x3c778e0ea7c5c5df?sa=X&ved=1t:57443&ictx=111")
                    )
                ]
            ),
        )
        output_list.append(bubble)
    return output_list


def gen_flex_jaycompare_list(data):
    output_list = []
    for product in data:
        bubble = FlexBubble(
            direction='ltr',
            body=FlexBox(
                layout='vertical',
                contents=[
                    # title
                    FlexText(text=str(product["product_name"]), weight='bold', size='md'),
                    # info
                    FlexBox(
                        layout='vertical',
                        margin='lg',
                        spacing='sm',
                        contents=[
                            FlexBox(
                                layout='baseline',
                                spacing='sm',
                                contents=[
                                    FlexText(
                                        text='Price',
                                        color='#aaaaaa',
                                        size='sm',
                                        flex=1
                                    ),
                                    FlexText(
                                        text='฿'+str(int(product["price"])),
                                        wrap=True,
                                        color='#666666',
                                        size='sm',
                                        flex=5
                                    )
                                ],
                            ),
                        ],
                    )
                ],
            ),
            footer=FlexBox(
                layout='vertical',
                spacing='sm',
                contents=[
                    # callAction
                    FlexButton(
                        style='link',
                        height='sm',
                        action=URIAction(label='ซื้อเลย', uri=str(product["url"])),
                    ),
                    # separator
                    FlexSeparator(),
                    # websiteAction
                    FlexButton(
                        style='link',
                        height='sm',
                        action=MessageAction(label='Review', text='ขอรีวิวของมือถือรุ่น ' + product["product_name"] ),
                    )
                ]
            ),
        )
        output_list.append(bubble)
    return output_list

def gen_jreview_flex_product_list(data, answer_list):
    output_list = []
    for product in data:
        review_body = []
        for index, item in enumerate(answer_list):
            print(item)
            review_chuck = FlexBox(
                                    layout='baseline',
                                    spacing='sm',
                                    contents=[
                                        FlexText(
                                            text=str(index+1) +". ",
                                            color='#D32F2F',
                                            size='sm',
                                            flex=1
                                        ),
                                        FlexText(
                                            text=item[1:].replace(".", ""),
                                            wrap=True,
                                            color='#666666',
                                            size='sm',
                                            flex=5
                                        )
                                    ],
                                )
            review_body.append(review_chuck)
        bubble = FlexBubble(
            direction='ltr',
            size='giga',
            header=FlexBox(
                layout='vertical',
                spacing='sm',
                contents=[
                    # callAction
                    FlexText(text="รีวิว " + str(product["product_name"]), weight='bold', size='xl',color='#FFFFFF'),
                ],
                backgroundColor='#D32F2F',
                paddingAll='20px'
            ),
            hero=FlexImage(
                url=str(product["image"]),
                size='full',
                aspect_ratio='1:1',
                position='relative',
                aspect_mode='cover',
                action=MessageAction(label='Review', text='ขอรีวิวของมือถือรุ่น ' + product["product_name"] )
            ),
            body=FlexBox(
                layout='vertical',
                contents=[
                    # title
                    FlexText(text="จุดเด่นสำคัญสำหรับผู้ซื้อทั่วไป", weight='bold', size='md', margin='md'),
                    # info
                    FlexBox(
                        layout='vertical',
                        margin='lg',
                        spacing='sm',
                        contents=review_body,
                    ),
                    FlexText(text="เหมาะสำหรับนักเรียน นักศึกษา มืออาชีพ และผู้ที่ชื่นชอบงานครีเอทีฟ!",wrap=True,color='#4CAF50', size='xs', margin='md')
                ],
            )
            ,
            footer=FlexBox(
                layout='vertical',
                spacing='sm',
                contents=[
                    # callAction
                    FlexButton(
                        style='primary',
                        type='button',
                        height='sm',
                        action=URIAction(label='ซื้อเลย', uri=str(product["url"])),
                        color="#D32F2F"
                    ),
                    # separator
                    FlexSeparator(),
                    # websiteAction
                    FlexButton(
                        style='secondary',
                        type='button',
                        height='sm',
                        action=URIAction(label='อ่านเพิ่มเติม', uri=str(product["url"]))
                    )
                ]
            ),
        )
        output_list.append(bubble)
    return output_list

def gen_product_recommendation_text(data):
    str_output = "ทางเราแนะนำ "
    prod_num = len(data)
    for index, item in enumerate(data):
        # Add a comma after every element except the last one
        if index < prod_num - 1:
            str_output += str(item["product_name"]) + ", "
        else:
            str_output += str(item["product_name"])
    print(str_output)
    return str_output



@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    text = event.message.text
    if text == 'table':
        prompt = "can you compare samsung galaxy A06 and samsung galaxy A05 in table format? with the same indentation on every row"

        # The payload to be provided to Bedrock 
        body = json.dumps({
            "inputText": prompt,
            "textGenerationConfig": {
                "stopSequences": [],
                "temperature": 0,
                "topP": 0.9
            }
        })

        # The actual call to retrieve an answer from the model
        response = bedrock_runtime.invoke_model(
            body=body,
            modelId="amazon.titan-text-premier-v1:0",
            accept='application/json',
            contentType='application/json'
        )
        print(response)

        response_body = json.loads(response.get('body').read())
        print(response_body)

        # The response from the model now mapped to the answer
        answer = response_body.get('results')[0].get('outputText')
        print(answer)
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=str(answer))]
                )
            )
    elif ('1.' in text) and ('2.' in text):
        result = retrieve_and_generate(input=event.message.text, knowledge_base_id=os.getenv('Bedrock_kb_product_id'), model_arn=model_arn,prompt=prompt_product_id_search, sessionId='')
        result_pd_id_text = result['output']['text']
        product_id_list = extract_product_id(result_pd_id_text)
        pd_detail = get_product_detail(table_feature, product_id_list)
        pd_info_detail = get_product_detail(table, product_id_list)
        flex_list = gen_flex_jaycompare_list(pd_info_detail)
        flex_carousel = FlexCarousel(type='carousel',contents=flex_list)
        product_flex_table_list = [
                            FlexBox(
                                layout='horizontal',
                                contents=[
                                    FlexText(
                                        text='รุ่น',
                                        size='sm',
                                        color='#FFFFFF',
                                        flex=2,
                                        weight='bold'
                                    ),
                                    FlexText(
                                        text='ขนาด',
                                        size='sm',
                                        color='#FFFFFF',
                                        flex=1,
                                        align='center',
                                        weight='bold'
                                    ),
                                    FlexText(
                                        text='ความจุ',
                                        size='sm',
                                        color='#FFFFFF',
                                        flex=1,
                                        align='center',
                                        weight='bold'
                                    ),
                                    FlexText(
                                        text='5G',
                                        size='sm',
                                        color='#FFFFFF',
                                        flex=1,
                                        align='center',
                                        weight='bold'
                                    ),
                                    FlexText(
                                        text='ราคา',
                                        size='sm',
                                        color='#FFFFFF',
                                        flex=1,
                                        align='center',
                                        weight='bold'
                                    )
                                ]
                            )]
        for item in pd_detail:
            product_review = FlexBox(
                                    layout='horizontal',
                                    contents=[
                                        FlexText(
                                            text=item["product_name"],
                                            size='xs',
                                            color='#FFFFFF',
                                            flex=2
                                        ),
                                        FlexText(
                                            text=item["size"],
                                            size='xs',
                                            color='#FFFFFF',
                                            flex=1,
                                            align='center'
                                        ),
                                        FlexText(
                                            text=item["capacity"]+'GB',
                                            size='xs',
                                            color='#FFFFFF',
                                            flex=1,
                                            align='center'
                                        ),
                                        FlexText(
                                            text=('✓' if item["5g_flag"] == 1 else '✗'),
                                            size='sm',
                                            color=('#4CAF50' if item["5g_flag"] == 1 else '#F44336'),
                                            flex=1,
                                            align='center'
                                        ),
                                        FlexText(
                                            text='฿' + str(item["price"]),
                                            size='xs',
                                            color='#FFFFFF',
                                            flex=1,
                                            align='center'
                                        )
                                    ]
                                )
            product_flex_table_list.append(product_review)
        jaycompare_bubble = FlexBubble(
            size='giga',
            body=FlexBox(
                layout='vertical',
                background_color='#61030A',
                contents=[
                    FlexText(
                        text='ตารางเปรียบเทียบสินค้า',
                        weight='bold',
                        size='xl',
                        color='#FFFFFF',
                        align='center'
                    ),
                    FlexBox(
                        layout='vertical',
                        margin='lg',
                        spacing='sm',
                        contents=product_flex_table_list
                    )
                ],
                border_width='medium',
                corner_radius='none'
            )
        )
        # To send this bubble, you would typically use:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[FlexMessage(alt_text="jaycompare", contents=jaycompare_bubble), FlexMessage(alt_text="jaycompare", contents=flex_carousel)]
                )
            )
    elif text == 'สอบถามทั่วไป':
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text="คุณลูกค้าสามารถสอบถามเพื่อให้ร้านแนะนำสินค้าได้เลยค่ะ")]
                )
            )
    elif text == 'เปรียบเทียบสินค้า':
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text="ใส่ชื่อสินค้าที่ต้องการเปรียบเทียบ\n 1. สินค้าชิ้นที่ 1\n 2. สินค้าชิ้นที่ 2\n 3. สินค้าชิ้นที่ 3\n 4. สินค้าชิ้นที่ 4")]
                )
            )
    elif text == 'รีวิวสินค้า':
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text='คุณลูกค้าสามารถพิมพ์ว่ารีวิวตามด้วยชื่อสินค้าได้เลยค่ะ\n ตัวอย่าง\n "รีวิว iPhone 16 Pro Max"')]
                )
            )
    elif 'รีวิว' in text:
        translate = boto3.client('translate')
        result = retrieve_and_generate(input=event.message.text + " ตอบเป็นภาษาอังกฤษ", knowledge_base_id=os.getenv('Bedrock_kb_id'),prompt=prompt_string, model_arn=model_arn, sessionId='')
        generated_text = result['output']['text']
        print("result: " , generated_text, result['sessionId'])
        prompt = "4 bullet point " + generated_text
        # The payload to be provided to Bedrock 
        body = json.dumps({
            "inputText": prompt,
            "textGenerationConfig": {
                "stopSequences": [],
                "temperature": 0,
                "topP": 0.9
            }
        })
        # The actual call to retrieve an answer from the model
        response = bedrock_runtime.invoke_model(
            body=body,
            modelId="amazon.titan-text-premier-v1:0",
            accept='application/json',
            contentType='application/json'
        )
        response_body = json.loads(response.get('body').read())
        answer = response_body.get('results')[0].get('outputText')
        result_pd_id = retrieve_and_generate(input=generated_text, knowledge_base_id=os.getenv('Bedrock_kb_product_id'), model_arn=model_arn, prompt=prompt_product_id_search,sessionId='')
        result_pd_id_text = result_pd_id['output']['text']
        print("result text: "+result_pd_id_text)
        print("Extracted product id:", result_pd_id_text)
        thai_version_output = translate.translate_text(
            Text=answer,
            SourceLanguageCode='auto',  # Auto-detect source language
            TargetLanguageCode='th'
        )
        answer_list = [line.strip() for line in thai_version_output.get("TranslatedText").split('\n') if line.strip()]
        product_id_list = extract_product_id(result_pd_id_text)
        if len(product_id_list) == 0:
            output_str = thai_version_output.get("TranslatedText")
            messages_output = [TextMessage(text=output_str)]
        else:
            if len(product_id_list) > 5:
                product_id_list = random.sample(product_id_list, 5)
            pd_detail = get_product_detail(table, product_id_list)
            if len(pd_detail) == 0:
                output_str = "รีวิว\n" + thai_version_output.get("TranslatedText")
                messages_output = [TextMessage(text=output_str)]
            else:
                for product in pd_detail:
                    print(pd_detail)
                flex_list = gen_jreview_flex_product_list(pd_detail, answer_list)
                flex_carousel = FlexCarousel(type='carousel',contents=flex_list)
                messages_output = [FlexMessage(alt_text="jayreview", contents=flex_carousel)]
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=messages_output
                )
            )
        # with open('/opt/config/jayreview.json', 'r', encoding='utf-8') as file:
        #     json_string = file.read()
        # with ApiClient(configuration) as api_client:
        #     line_bot_api = MessagingApi(api_client)
        #     message = FlexMessage(alt_text="jayreview", contents=FlexContainer.from_json(json_string))
        #     line_bot_api.reply_message(
        #         ReplyMessageRequest(
        #             reply_token=event.reply_token,
        #             messages=[message]
        #         )
        #     )

    else:
        translate = boto3.client('translate')
        eng_version_input = translate.translate_text(
            Text=event.message.text,
            SourceLanguageCode='auto',  # Auto-detect source language
            TargetLanguageCode='en'
        )
        print("thai version of text input: ", eng_version_input.get("TranslatedText"), '\n')
        # result = retrieve_and_generate(input=eng_version_input.get("TranslatedText"), knowledge_base_id=os.getenv('Bedrock_kb_id'), model_arn=model_arn, sessionId=sessionID)
        # Example usage:
        result = retrieve_and_generate(input=event.message.text + " ตอบเป็นภาษาอังกฤษ" + " please answer within 3 sentence", knowledge_base_id=os.getenv('Bedrock_kb_id'), model_arn=model_arn,prompt=prompt_string, sessionId='')
        generated_text = result['output']['text']
        print("result: " , generated_text, result['sessionId'])
        result_pd_id = retrieve_and_generate(input=generated_text, knowledge_base_id=os.getenv('Bedrock_kb_product_id'), model_arn=model_arn, prompt=prompt_product_id_search, sessionId='')
        result_pd_id_text = result_pd_id['output']['text']
        print("result text: "+result_pd_id_text)
        print("Extracted product id:", result_pd_id_text)
        thai_version_output = translate.translate_text(
            Text=generated_text,
            SourceLanguageCode='auto',  # Auto-detect source language
            TargetLanguageCode='th'
        )
        if (len(thai_version_output.get("TranslatedText")) > 299):
            output_review = thai_version_output.get("TranslatedText")[:299]
        else:
            output_review = thai_version_output.get("TranslatedText")
        product_id_list = extract_product_id(result_pd_id_text)
        if len(product_id_list) == 0:
            output_str = thai_version_output.get("TranslatedText")
            messages_output = [TextMessage(text=output_str)]
        else:
            if len(product_id_list) > 5:
                product_id_list = random.sample(product_id_list, 5)
            pd_detail = get_product_detail(table, product_id_list)
            if len(pd_detail) == 0:
                output_str = thai_version_output.get("TranslatedText")
                messages_output = [TextMessage(text=output_str)]
            else:
                for product in pd_detail:
                    print(pd_detail)
                flex_list = gen_flex_product_list(pd_detail)
                flex_carousel = FlexCarousel(type='carousel',contents=flex_list)
                output_str = gen_product_recommendation_text(pd_detail) + '\n ด้วยสาเหตุว่า ' + thai_version_output.get("TranslatedText")
                messages_output = [FlexMessage(alt_text="Recommendation", contents=flex_carousel), TextMessage(text=output_str)]
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=messages_output
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