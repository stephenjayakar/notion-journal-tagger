import pickle
import os
from typing import List
from main import PageContent, PageTags

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
