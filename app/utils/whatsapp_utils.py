import logging
from flask import current_app, jsonify
import json
import requests
import base64
from openai import OpenAI

from langchain_openai import ChatOpenAI
from PyPDF2 import PdfReader
from langchain.text_splitter import RecursiveCharacterTextSplitter
import chromadb

client = chromadb.PersistentClient(path="app/chromadb_data")
llm = ChatOpenAI()
openai_client=OpenAI()
collection = client.get_or_create_collection(name="test1")
# from app.services.openai_service import generate_response
import re


def log_http_response(response):
    logging.info(f"Status: {response.status_code}")
    logging.info(f"Content-type: {response.headers.get('content-type')}")
    logging.info(f"Body: {response.text}")


def get_text_message_input(recipient, text):
    print("yessss")
    return json.dumps(
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
    )


def generate_response(response):
    # Return text in uppercase
    results = collection.query(
            query_texts=[response],
            n_results=18
            )["documents"][0]
    print("chunks >>>>>>>",results)
    message_to_send=llm.invoke(f"You have to give answer only from the given data do not use your own knnowledge ,  if question are like hi, hello then just simply respond them acording to you  \n\n here is my question {response} , \n\n here is the data {results}").content
    return message_to_send


def send_message(data):
    headers = {
        "Content-type": "application/json",
        "Authorization": f"Bearer {current_app.config['ACCESS_TOKEN']}",
    }

    url = f"https://graph.facebook.com/{current_app.config['VERSION']}/{current_app.config['PHONE_NUMBER_ID']}/messages"

    try:
        response = requests.post(
            url, data=data, headers=headers, timeout=10
        )  # 10 seconds timeout as an example
        response.raise_for_status()  # Raises an HTTPError if the HTTP request returned an unsuccessful status code
    except requests.Timeout:
        logging.error("Timeout occurred while sending message")
        return jsonify({"status": "error", "message": "Request timed out"}), 408
    except (
        requests.RequestException
    ) as e:  # This will catch any general request exception
        logging.error(f"Request failed due to: {e}")
        return jsonify({"status": "error", "message": "Failed to send message"}), 500
    else:
        # Process the response as normal
        log_http_response(response)
        return response


def process_text_for_whatsapp(text):
    # Remove brackets
    pattern = r"\【.*?\】"
    # Substitute the pattern with an empty string
    text = re.sub(pattern, "", text).strip()

    # Pattern to find double asterisks including the word(s) in between
    pattern = r"\*\*(.*?)\*\*"

    # Replacement pattern with single asterisks
    replacement = r"*\1*"

    # Substitute occurrences of the pattern with the replacement
    whatsapp_style_text = re.sub(pattern, replacement, text)

    return whatsapp_style_text
def download_media_by_id(message_id,type_of_message):
    url = f"https://graph.facebook.com/v19.0/{message_id}"
    headers = {
        "Authorization": f"Bearer {current_app.config['ACCESS_TOKEN']}"}
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        json_string=response.content
        json_string = json_string.decode('utf-8')

        # Parse JSONß
        data = json.loads(json_string)

        # Extract URL
        url = data['url']
    

    else:
        logging.error(f"Failed to download image: {response.status_code}")
    attachment_url = url
    response = requests.get(attachment_url, headers=headers)


    if response.status_code == 200 and type_of_message=="image":
        with open("app/images/data.jpg", "wb") as file:
            file.write(response.content)
        print("Image downloaded successfully.")
    if response.status_code == 200 and type_of_message=="document":
        print("downlading pdf")
        with open("app/documents_pdf/content.pdf", "wb") as file:
            file.write(response.content)
        print("pdf downloaded successfully.")
    else:
        print("Failed to download the other catagory. Status code:", response.status_code)
        print("Response content:", response.content)
    return response.content
        

def process_whatsapp_message(body):
    type_of_message = body["entry"][0]["changes"][0]["value"]["messages"][0]["type"]
    print("full query",body["entry"][0]["changes"][0]["value"]["messages"][0])

    

    if type_of_message=="text":
        message = body["entry"][0]["changes"][0]["value"]["messages"][0]
            
        message_body = message["text"]["body"]
 

        # TODO: implement custom function here
        response = generate_response(message_body)

        # OpenAI Integration
        # response = generate_response(message_body, wa_id, name)
        # response = process_text_for_whatsapp(response)

        data = get_text_message_input(current_app.config["RECIPIENT_WAID"], response)
        print("data",data)
        send_message(data)
    if type_of_message=="image":
        message_id=body["entry"][0]["changes"][0]["value"]["messages"][0]["image"]["id"]
        download_media_by_id(message_id,type_of_message)
        try:
            caption=body["entry"][0]["changes"][0]["value"]["messages"][0]["image"]["caption"]
            response=image_processor(caption,"app/images/image.jpg")
            data = get_text_message_input(current_app.config["RECIPIENT_WAID"], response)
            send_message(data)  
        except:
            print("downlaoded photo but didnot got any text with image ")
            return "only downloaded without caption"
    elif type_of_message == "document":
       
        print("document taking away")
        document_id = body["entry"][0]["changes"][0]["value"]["messages"][0]["document"]["id"]

        download_media_by_id(document_id,type_of_message)
        # SAVING TO CHROMDB

        try:
            extracted_text = extract_text_from_pdf("app/documents_pdf/content.pdf")
            print(extracted_text)
        except Exception as e:
            print("Error:", e)
        text_splitter = RecursiveCharacterTextSplitter(
            # Set a really small chunk size, just to show.
            chunk_size=7000,
            chunk_overlap=100,
            length_function=len,
            is_separator_regex=False,
        )

        """ 
        Now to add data in chroma we need a list of documents and its corresponding ids as (iD1,iD2,iD3 ....) so the below code is there for id generation 
        """
        print(extracted_text)
        chunked_documents = text_splitter.split_text(extracted_text)
        ids = [f"id{i}" for i in range(1, len(chunked_documents) + 1)]
        print(type(ids[0]))
        collection.add(
        documents=chunked_documents,
        ids=ids
        )

        print("doument added successfully")
        data = get_text_message_input(current_app.config["RECIPIENT_WAID"], "You Succesfully Added Your Document Now you can ask any question !")
        send_message(data) 
        
        # Process the document (implement your logic here)
        # response = process_document(filename) 
        
        # # Send a response message
        # data = get_text_message_input(current_app.config["RECIPIENT_WAID"], response)
        # send_message(data)

    else:
        # Handle other message types or unsupported types
        print(f"Unsupported message type: {type_of_message}")
                



def is_valid_whatsapp_message(body):
    """
    Check if the incoming webhook event has a valid WhatsApp message structure.
    """
    return (
        body.get("object")
        and body.get("entry")
        and body["entry"][0].get("changes")
        and body["entry"][0]["changes"][0].get("value")
        and body["entry"][0]["changes"][0]["value"].get("messages")
        and body["entry"][0]["changes"][0]["value"]["messages"][0]
    )


def encode_image(image_path):
  with open(image_path, "rb") as image_file:
    return base64.b64encode(image_file.read()).decode('utf-8')
  

def image_processor(message,path_of_image): 
    "Useful for when you need explain something about image"
    base64_image = encode_image(path_of_image)
    image=f"data:image/jpeg;base64,{base64_image}"      
    response = openai_client.chat.completions.create(
    model="gpt-4-vision-preview",
    messages=[
    {
        "role": "user",
        "content": [
        {"type": "text", "text": message},
        {
            "type": "image_url",
            "image_url": {
            "url": image,
            },
        },
        ],
    }
    ],
    max_tokens=2000,
    ).choices[0].message.content
    print(response)
    return response
def extract_text_from_pdf(pdf_path):
    text = ''
    with open(pdf_path, 'rb') as file:
        reader = PdfReader(file)
        for page in reader.pages:
            text += page.extract_text()
    return text