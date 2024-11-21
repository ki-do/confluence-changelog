import requests
import json
from datetime import datetime
import base64
import argparse
import time

CONFLUENCE_BASE_URL = "https://factory-x.atlassian.net/wiki"
headers = {}

def get_page_version(page_id):
    versions = []
    start = 0
    limit = 500
    while True:
        url = f"{CONFLUENCE_BASE_URL}/rest/api/content/{page_id}/version?start={start}&limit={limit}"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        version_data = response.json()
        
        for version in version_data['results']:
            version_number = version['number']
            author = version['by']['displayName']
            when = version['when']
            versions.append((version_number, author, when))
        
        if len(version_data['results']) < limit:
            break
        
        start += limit

    return versions

def log_changes(page_id):
    versions = get_page_version(page_id)

    url = f"{CONFLUENCE_BASE_URL}/rest/api/content/{page_id}"
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    page_data = response.json()
    title = page_data['title']

    log_url = f"{CONFLUENCE_BASE_URL}/rest/api/content/{log_page_id}?expand=version,body.storage"
    log_response = requests.get(log_url, headers=headers)
    log_response.raise_for_status()
    log_data = log_response.json()
    current_body = log_data['body']['storage']['value']

    table_rows = ""
    for version_number, author, when in versions:
        version_link = f"{CONFLUENCE_BASE_URL}{page_data['_links']['webui']}?pageVersion={version_number}"
        formatted_when = datetime.strptime(when, "%Y-%m-%dT%H:%M:%S.%fZ").strftime("%Y-%m-%dT%H:%M:%S")
        table_rows += f"""
        <tr>
            <td><a href="{version_link}">{title}</a></td>
            <td>{version_number}</td>
            <td>{author}</td>
            <td>{formatted_when}</td>
        </tr>
        """

    if "<table" not in current_body:
        updated_body = f"""
        {current_body}
        <h2>Change Log</h2>
        <table border="1" style="width:100%;border-collapse:collapse;">
            <tr>
                <th>Page Title</th>
                <th>Version</th>
                <th>Author</th>
                <th>Date</th>
            </tr>
            {table_rows}
        </table>
        """
    else:
        updated_body = current_body.replace("</table>", f"{table_rows}</table>")

    new_version = log_data['version']['number'] + 1
    update_payload = {
        "version": {"number": new_version},
        "title": log_data['title'],
        "type": "page",
        "body": {
            "storage": {
                "value": updated_body,
                "representation": "storage"
            }
        }
    }

    update_url = f"{CONFLUENCE_BASE_URL}/rest/api/content/{log_page_id}"
    update_response = requests.put(update_url, headers=headers, data=json.dumps(update_payload))
    update_response.raise_for_status()

    #print("Changelog updated successfully!")

def monitor_pages():
    for page_id in pages_to_monitor:
        try:
            get_page_version(page_id)   
            log_changes(page_id)         
            
            #if page_id not in latest_versions or version_number > latest_versions[page_id]:
                #latest_versions[page_id] = version_number
                #change_time = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")
                #log_message = f"* [{title}](https://{CONFLUENCE_BASE_URL}{page_url}) was updated on {change_time} (Version {version})"
                #log_changes(page_id)
                #print(f"Logged change for {title}.")
                
        except requests.exceptions.RequestException as e:
            #print(f"Error monitoring page {page_id}: {e}")
            pass

def get_child_pages(parent_id):
    url = f"{CONFLUENCE_BASE_URL}/rest/api/content/{parent_id}/child/page?limit=50"
    response = requests.get(url, headers=headers)
    response.raise_for_status()

    child_pages = response.json().get("results", [])
    return [(page["id"], page["title"]) for page in child_pages]

def get_all_descendant_pages(parent_id):
    all_descendants = []

    children = get_child_pages(parent_id)

    for child_id, child_title in children:
        all_descendants.append((child_id, child_title))

        child_descendants = get_all_descendant_pages(child_id)
        all_descendants.extend(child_descendants)

    return all_descendants

def clear_page_content(page_id):
    url = f"{CONFLUENCE_BASE_URL}/rest/api/content/{page_id}?expand=version,body.storage"
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    page_data = response.json()

    current_version = page_data['version']['number']
    page_title = page_data['title']

    update_payload = {
        "version": {"number": current_version + 1},
        "title": page_title,
        "type": "page",
        "body": {
            "storage": {
                "value": "",  
                "representation": "storage"
            }
        }
    }

    update_url = f"{CONFLUENCE_BASE_URL}/rest/api/content/{page_id}"
    update_response = requests.put(update_url, headers=headers, data=json.dumps(update_payload))
    update_response.raise_for_status()

    print(f"Content of page ID {page_id} has been cleared.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect changes from the pages in confluence and summarize them in a table")
    parser.add_argument("--email", required=True, help="Your Confluence email address")
    parser.add_argument("--api_token", required=True, help="Confluence API token for authentication")
    parser.add_argument("--include", required=True, help="Confluence PageID of the root page to include in the crawling process")
    parser.add_argument("--exclude", required=False, help="Confluence PageID of the root page to exclude from the crawling process")
    parser.add_argument("--logpage", required=True, help="Confluence PageID to collect the logs")

    args = parser.parse_args()
    EMAIL = args.email
    API_TOKEN = args.api_token
    input_string = EMAIL+":"+API_TOKEN

    encoded_bytes = base64.b64encode(input_string.encode("utf-8"))
    encoded_auth_string = encoded_bytes.decode("utf-8")

    headers = {
        "Authorization": f"Basic " + encoded_auth_string,
        "Content-Type": "application/json"
    }

    #parent_id = "182091808"  
    parent_id = args.include
    all_descendants = get_all_descendant_pages(parent_id)
    exclude_id = args.exclude
    exclude_pages = get_all_descendant_pages(exclude_id)
    log_page_id = args.logpage

    clear_page_content(log_page_id)

    pages_to_monitor = []
    #log_page_id = "204046352" 

    latest_versions = {}

    for page_id, title in all_descendants:
        pages_to_monitor.append(page_id)
    pages_to_monitor.remove(log_page_id)
    for page_id, title in exclude_pages:
        if page_id in pages_to_monitor:
            pages_to_monitor.remove(page_id)
            #print(f"Removed: {title}")
    #print(f"Pages to monitor IDs: {pages_to_monitor}")


    start_time = time.time()
    monitor_pages()
    end_time = time.time()

    execution_time = end_time - start_time
    print(f"done in {execution_time:.5f} seconds")
