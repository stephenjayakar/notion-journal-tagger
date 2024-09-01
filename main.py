import os
import sys
import pickle
from typing import List, Optional, Tuple
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
    title: Optional[str] = None
    content: Optional[str] = None

@dataclass
class PageTags:
    page_id: str
    new_tags: Optional[List[str]] = None
    written: bool = False

def read_tags_from_env() -> List[str]:
    tags_string = os.environ.get("TAGS", "")
    return [tag.strip() for tag in tags_string.split(',') if tag.strip()]

def read_additional_context_from_env() -> str:
    return os.environ.get("ADDITIONAL_CONTEXT", "")

def get_database_pages(database_id: str) -> List[dict]:
    pages = []
    start_cursor = None
    while True:
        response = notion_client.databases.query(
            database_id=database_id,
            start_cursor=start_cursor,
            page_size=100
        )
        pages.extend([{'id': page['id'], 'title': page['properties']['Name']['title'][0]['plain_text'] if page['properties']['Name']['title'] else ''} for page in response['results']])
        if not response.get('has_more'):
            break
        start_cursor = response.get('next_cursor')
    return pages

def get_notion_page_content(page_id: str) -> Tuple[str, str]:
    page = notion_client.pages.retrieve(page_id)
    title = page['properties']['Name']['title'][0]['plain_text'] if page['properties']['Name']['title'] else ''
    
    block_children = notion_client.blocks.children.list(page_id)
    
    content = ""
    for block in block_children["results"]:
        if block["type"] == "paragraph":
            rich_text = block["paragraph"]["rich_text"]
            if rich_text:  # Check if rich_text is not empty
                content += rich_text[0]["plain_text"] + "\n\n"
        elif block["type"] == "bulleted_list_item":
            rich_text = block["bulleted_list_item"]["rich_text"]
            if rich_text:  # Check if rich_text is not empty
                content += "- " + rich_text[0]["plain_text"] + "\n"

    return title, content.strip()

def save_data(data: List, filename: str):
    with open(os.path.join('output', filename), 'wb') as f:
        pickle.dump(data, f)

def load_data(filename: str) -> List:
    with open(os.path.join('output', filename), 'rb') as f:
        return pickle.load(f)

def get_tags_from_ai(title: str, content: str, tags: List[str], additional_context: str) -> List[str]:
    system_message = """You are an AI assistant that labels content with appropriate tags. Please analyze the given title and content and assign relevant tags from the provided list. Be conservative in your tag selection:
    - Only assign tags if there's a medium to strong correlation with the title and content.
    - It's better to assign fewer tags or even no tags than to assign irrelevant ones.
    - Consider the context and overall theme of the content, not just keyword matches.
    - If you're unsure about a tag, it's better to omit it."""

    user_message = f"Title: {title}\n\nContent to label:\n\n{content}\n\nAdditional context: {additional_context}\n\nAvailable tags: {', '.join(tags)}\n\nPlease label this content with appropriate tags, being cautious and selective in your choices."

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message}
    ]

    model = os.environ.get("OPENAI_MODEL", "gpt-4o-2024-08-06")  # Default to gpt-4-0613 if not specified

    completion = openai_client.chat.completions.create(
        model=model,
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
        print(f"Title: {content.title}")
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
    additional_context = read_additional_context_from_env()
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
        pages = get_database_pages(database_id)
        content_data = [PageContent(page['id'], title=page['title']) for page in pages]
        tags_data = [PageTags(page['id']) for page in pages]
        save_data(content_data, 'page_content.pkl')
        save_data(tags_data, 'page_tags.pkl')
        print(f"Phase 1 complete. {len(content_data)} pages saved.")

    elif phase == '2':
        content_data = load_data('page_content.pkl')
        for i, page_content in enumerate(content_data):
            title, content = get_notion_page_content(page_content.page_id)
            content_data[i].title = title
            content_data[i].content = content
            print(f"Processed {i+1}/{len(content_data)} pages")
        save_data(content_data, 'page_content.pkl')
        print(f"Phase 2 complete. Content retrieved for {len(content_data)} pages.")

    elif phase == '3':
        content_data = load_data('page_content.pkl')
        tags_data = load_data('page_tags.pkl')
        for i, (page_content, page_tags) in enumerate(zip(content_data, tags_data)):
            if page_content.content:
                new_tags = get_tags_from_ai(page_content.title, page_content.content, tags, additional_context)
                tags_data[i].new_tags = new_tags
            print(f"Processed {i+1}/{len(content_data)} pages")
        save_data(tags_data, 'page_tags.pkl')
        print(f"Phase 3 complete. Tags assigned to {len([d for d in tags_data if d.new_tags])} pages.")

    elif phase == '4':
        tags_data = load_data('page_tags.pkl')

        # Get the current database schema
        database = notion_client.databases.retrieve(database_id)
        existing_tags = [option['name'] for option in database['properties']['Tags']['multi_select']['options']]

        # Add new tags to the database if they don't exist
        new_tags = set(tags) - set(existing_tags)
        if new_tags:
            updated_options = database['properties']['Tags']['multi_select']['options'] + [{"name": tag} for tag in new_tags]
            notion_client.databases.update(
                database_id=database_id,
                properties={
                    "Tags": {
                        "multi_select": {
                            "options": updated_options
                        }
                    }
                }
            )
            print(f"Added {len(new_tags)} new tags to the database.")

        # Update pages with their respective tags
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
