import pickle
import os
from typing import List
from main import (
    PageContent, PageTags, read_tags_from_env, get_notion_page_content,
    get_tags_from_ai, update_notion_page, read_additional_context_from_env
)

def process_single_page(page_id: str):
    tags = read_tags_from_env()
    additional_context = read_additional_context_from_env()
    database_id = os.environ.get("NOTION_DATABASE_ID")

    if not database_id:
        print("Error: NOTION_DATABASE_ID not set in environment variables.")
        exit()

    # Phase 1: Initialize PageContent and PageTags for the single page
    content_data = PageContent(page_id)
    tags_data = PageTags(page_id)

    # Phase 2: Retrieve content and title for the single page
    title, content = get_notion_page_content(page_id)
    content_data.content = content
    content_data.title = title
    print(f"Phase 2 complete. Content and title retrieved for page {page_id}.")

    # Phase 3: Assign tags using AI for the single page
    if content_data.content:
        new_tags = get_tags_from_ai(content_data.title, content_data.content, tags, additional_context)
        tags_data.new_tags = new_tags
    print(f"Phase 3 complete. Tags assigned to page {page_id}.")

    # Phase 4: Update the Notion page with the new tags
    if tags_data.new_tags:
        update_notion_page(tags_data.page_id, tags_data.new_tags)
        tags_data.written = True
    print(f"Phase 4 complete. Tags written to Notion for page {page_id}.")

def load_data(filename: str) -> List:
    with open(os.path.join('output', filename), 'rb') as f:
        return pickle.load(f)

def check_missing_tags():
    tags_data = load_data('page_tags.pkl')
    content_data = load_data('page_content.pkl')
    
    pages_without_tags = [
        (page.page_id, next((content.content for content in content_data if content.page_id == page.page_id), "No content"))
        for page in tags_data if not page.new_tags
    ]

    if pages_without_tags:
        print("Pages without tags:")
        for page_id, content in pages_without_tags:
            print(f"Page ID: {page_id}")
            print(f"Content Snippet: {content[:100]}..." if content else "No content")
            print("---")
    else:
        print("All pages have tags.")

def extract_notion_id(url: str) -> str:
    # Split the URL by '-' and get the last part
    parts = url.split('-')
    if len(parts) > 1:
        # The ID is the last part, remove any query parameters
        return parts[-1].split('?')[0]
    else:
        # If there's no '-', split by '/' and get the last part
        parts = url.split('/')
        return parts[-1].split('?')[0]

