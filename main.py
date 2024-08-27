import os
from openai import OpenAI
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import List

load_dotenv()

client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
)

class TaggedContent(BaseModel):
    tags: List[str]

# Read input file
with open('input.md', 'r') as file:
    content = file.read()

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
response = client.beta.chat.completions.parse(
    model="gpt-4o-2024-08-06",
    messages=messages,
    response_format=TaggedContent,
)

# Extract the tags
assigned_tags = response.choices[0].message.parsed.tags

print("Assigned tags:", assigned_tags)
