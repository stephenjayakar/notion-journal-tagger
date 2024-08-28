import os
from openai import OpenAI
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import List
from notion_client import Client as NotionClient

load_dotenv()

openai_client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
)

notion_client = NotionClient(auth=os.environ.get("NOTION_API_KEY"))

class TaggedContent(BaseModel):
    tags: List[str]

# Function to read Notion page content
def get_notion_page_content(page_id):
    block_children = notion_client.blocks.children.list(page_id)
    
    content = ""
    for block in block_children["results"]:
        if block["type"] == "paragraph":
            content += block["paragraph"]["rich_text"][0]["plain_text"] + "\n\n"
    
    return content.strip()

# Notion page ID (you should replace this with the actual page ID)
notion_page_id = "cb8ec0877dd4407b844d1876b6474f7b"

# Get content from Notion
content = get_notion_page_content(notion_page_id)
print(content)
raise Exception("meow")

# List of tags
tags = ["Personal", "Dating", "Nadia", "Work", "Research", "Family", "Christianity", "Friends"]

# Prepare the message for the AI
system_message = "You are an AI assistant that labels content with appropriate tags. Please analyze the given content and assign relevant tags from the provided list. You can use multiple tags if appropriate."
user_message = f"Content to label:\n\n{content}\n\nAvailable tags: {', '.join(tags)}\n\nPlease label this content with appropriate tags."

messages = [
    {"role": "system", "content": system_message},
    {"role": "user", "content": user_message}
]

# Make the API call
response = openai_client.beta.chat.completions.parse(
    model="gpt-4o-2024-08-06",
    messages=messages,
    response_format=TaggedContent,
)

# Extract the tags
assigned_tags = response.choices[0].message.parsed.tags

print("Assigned tags:", assigned_tags)
