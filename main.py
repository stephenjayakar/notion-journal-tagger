import os
import sys
import pickle
from typing import List, Tuple, Optional
from dataclasses import dataclass
from openai import OpenAI
from dotenv import load_dotenv
from notion_client import Client as NotionClient

load_dotenv()

openai_client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
)

notion_client = NotionClient(auth=os.environ.get("NOTION_API_KEY"))

@dataclass
class PageData:
    page_id: str
    new_tags: Optional[List[str]] = None
    written: bool = False

def read_tags_from_file(filename: str) -> List[str]:
    with open(filename, 'r') as f:
        return [line.strip() for line in f if line.strip()]

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
            content += block["paragraph"]["rich_text"][0]["plain_text"] + "\n\n"
    
    return content.strip()

def save_data(data: List[PageData], filename: str):
    with open(os.path.join('output', filename), 'wb') as f:
        pickle.dump(data, f)

def load_data(filename: str) -> List[PageData]:
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
            "strict": True,
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
            }
        }
    )

    ai_response = completion.choices[0].message.content
    return ai_response['tags']

def update_notion_page(page_id: str, tags: List[str]):
    notion_client.pages.update(
        page_id=page_id,
        properties={
            "Tags": {"multi_select": [{"name": tag} for tag in tags]}
        }
    )

def print_debug_data(data: List[PageData]):
    for page_data in data:
        print(f"Page ID: {page_data.page_id}")
        print(f"New Tags: {page_data.new_tags}")
        print(f"Written: {page_data.written}")
        print("---")

def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py <phase> [database_id]")
        sys.exit(1)

    phase = sys.argv[1]
    tags = read_tags_from_file('tags.txt')

    if phase == 'debug':
        if len(sys.argv) < 3:
            print("For debug mode, please provide the phase file to load (1, 2, or 3)")
            sys.exit(1)
        debug_phase = sys.argv[2]
        if debug_phase == '1':
            filename = 'page_data.pkl'
        elif debug_phase == '2':
            filename = 'page_data_with_tags.pkl'
        elif debug_phase == '3':
            filename = 'page_data_final.pkl'
        else:
            print("Invalid debug phase. Please use 1, 2, or 3.")
            sys.exit(1)
        
        data = load_data(filename)
        print(f"Debug mode: Loaded {filename}")
        print_debug_data(data)
        sys.exit(0)

    if phase == '1':
        if len(sys.argv) < 3:
            print("For phase 1, please provide the database ID")
            sys.exit(1)
        database_id = sys.argv[2]
        page_ids = get_database_pages(database_id)
        data = [PageData(page_id) for page_id in page_ids]
        save_data(data, 'page_data.pkl')
        print(f"Phase 1 complete. {len(data)} pages saved.")

    elif phase == '2':
        data = load_data('page_data.pkl')
        for i, page_data in enumerate(data):
            content = get_notion_page_content(page_data.page_id)
            new_tags = get_tags_from_ai(content, tags)
            data[i].new_tags = new_tags
            print(f"Processed {i+1}/{len(data)} pages")
        save_data(data, 'page_data_with_tags.pkl')
        print(f"Phase 2 complete. Tags assigned to {len(data)} pages.")

    elif phase == '3':
        data = load_data('page_data_with_tags.pkl')
        for i, page_data in enumerate(data):
            if not page_data.written and page_data.new_tags:
                update_notion_page(page_data.page_id, page_data.new_tags)
                data[i].written = True
            print(f"Processed {i+1}/{len(data)} pages")
        save_data(data, 'page_data_final.pkl')
        print(f"Phase 3 complete. Tags written to Notion for {len([d for d in data if d.written])} pages.")

    else:
        print("Invalid phase. Please use 1, 2, 3, or debug.")

if __name__ == "__main__":
    main()
