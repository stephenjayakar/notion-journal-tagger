import os
import sys
import pickle
from typing import List, Optional
from dataclasses import dataclass
from openai import OpenAI
from dotenv import load_dotenv
from notion_client import Client as NotionClient
import json

load_dotenv()

openai_client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
)

notion_client = NotionClient(auth=os.environ.get("NOTION_API_KEY"))

@dataclass
class PageContent:
    page_id: str
    content: Optional[str] = None

@dataclass
class PageTags:
    page_id: str
    new_tags: Optional[List[str]] = None
    written: bool = False

def read_tags_from_env() -> List[str]:
    tags_string = os.environ.get("TAGS", "")
    return [tag.strip() for tag in tags_string.split(',') if tag.strip()]

def get_database_pages(database_id: str) -> List[str]:
    pages = []
    start_cursor = None
    while True:
        response = notion_client.databases.query(
            database_id=database_id,
            start_cursor=start_cursor,
            page_size=100
        )
        pages.extend([page['id'] for page in response['results']])
        if not response.get('has_more'):
            break
        start_cursor = response.get('next_cursor')
    return pages

def get_notion_page_content(page_id: str) -> str:
    block_children = notion_client.blocks.children.list(page_id)
    
    content = ""
    for block in block_children["results"]:
        if block["type"] == "paragraph":
            rich_text = block["paragraph"]["rich_text"]
            if rich_text:  # Check if rich_text is not empty
                content += rich_text[0]["plain_text"] + "\n\n"
    
    return content.strip()

def save_data(data: List, filename: str):
    with open(os.path.join('output', filename), 'wb') as f:
        pickle.dump(data, f)

def load_data(filename: str) -> List:
    with open(os.path.join('output', filename), 'rb') as f:
        return pickle.load(f)

def get_tags_from_ai(content: str, tags: List[str]) -> List[str]:
    system_message = "You are an AI assistant that labels content with appropriate tags. Please analyze the given content and assign relevant tags from the provided list. You can use multiple tags if appropriate."
    user_message = f"Content to label:\n\n{content}\n\nAvailable tags: {', '.join(tags)}\n\nPlease label this content with appropriate tags."

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message}
    ]

    completion = openai_client.chat.completions.create(
        model="gpt-4o-2024-08-06",
        messages=messages,
        response_format={
            "type": "json_schema",
            "json_schema": {
                # Generate a unique-ish name for the schema
                # TODO: Not great in that OpenAI will reuse the same 
                # schema for the same first 20 chars of tags.
                "name": "notion-journaler" + ''.join(tags)[:20],
                "schema": {
                "type": "object",
                "properties": {
                    "tags": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": tags
                        }
                    }
                },
                "required": ["tags"],
                "additionalProperties": False
            },
            "strict": True,
        }
        }
    )

    ai_response_dict = json.loads(completion.choices[0].message.content)
    return ai_response_dict['tags']

def update_notion_page(page_id: str, tags: List[str]):
    notion_client.pages.update(
        page_id=page_id,
        properties={
            "Tags": {"multi_select": [{"name": tag} for tag in tags]}
        }
    )

def print_debug_data(content_data: List[PageContent], tags_data: List[PageTags]):
    for content, tags in zip(content_data, tags_data):
        print(f"Page ID: {content.page_id}")
        print(f"Content: {content.content[:100]}..." if content.content else "No content")
        print(f"New Tags: {tags.new_tags}")
        print(f"Written: {tags.written}")
        print("---")

def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py <phase>")
        sys.exit(1)

    phase = sys.argv[1]
    tags = read_tags_from_env()
    database_id = os.environ.get("NOTION_DATABASE_ID")

    if not database_id:
        print("Error: NOTION_DATABASE_ID not set in environment variables.")
        sys.exit(1)

    if phase == 'debug':
        if len(sys.argv) < 3:
            print("For debug mode, please provide the phase file to load (1, 2, 3, or 4)")
            sys.exit(1)
        content_data = load_data('page_content.pkl')
        tags_data = load_data('page_tags.pkl')
        print(f"Debug mode: Loaded page_content.pkl and page_tags.pkl")
        print_debug_data(content_data, tags_data)
        sys.exit(0)

    if phase == '1':
        page_ids = get_database_pages(database_id)
        content_data = [PageContent(page_id) for page_id in page_ids]
        tags_data = [PageTags(page_id) for page_id in page_ids]
        save_data(content_data, 'page_content.pkl')
        save_data(tags_data, 'page_tags.pkl')
        print(f"Phase 1 complete. {len(content_data)} pages saved.")

    elif phase == '2':
        content_data = load_data('page_content.pkl')
        for i, page_content in enumerate(content_data):
            content = get_notion_page_content(page_content.page_id)
            content_data[i].content = content
            print(f"Processed {i+1}/{len(content_data)} pages")
        save_data(content_data, 'page_content.pkl')
        print(f"Phase 2 complete. Content retrieved for {len(content_data)} pages.")

    elif phase == '3':
        content_data = load_data('page_content.pkl')
        tags_data = load_data('page_tags.pkl')
        for i, (page_content, page_tags) in enumerate(zip(content_data, tags_data)):
            if page_content.content:
                new_tags = get_tags_from_ai(page_content.content, tags)
                tags_data[i].new_tags = new_tags
            print(f"Processed {i+1}/{len(content_data)} pages")
        save_data(tags_data, 'page_tags.pkl')
        print(f"Phase 3 complete. Tags assigned to {len([d for d in tags_data if d.new_tags])} pages.")

    elif phase == '4':
        tags_data = load_data('page_tags.pkl')
        for i, page_tags in enumerate(tags_data):
            if not page_tags.written and page_tags.new_tags:
                update_notion_page(page_tags.page_id, page_tags.new_tags)
                tags_data[i].written = True
            print(f"Processed {i+1}/{len(tags_data)} pages")
        save_data(tags_data, 'page_tags.pkl')
        print(f"Phase 4 complete. Tags written to Notion for {len([d for d in tags_data if d.written])} pages.")

    else:
        print("Invalid phase. Please use 1, 2, 3, 4, or debug.")

if __name__ == "__main__":
    main()
