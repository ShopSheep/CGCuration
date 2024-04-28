import json
import requests
import ssl
import time
import re
from bs4 import BeautifulSoup
from requests.exceptions import ConnectionError, ChunkedEncodingError, Timeout
from mysql.connector import connect
from multiprocessing import Pool, current_process
from openai import OpenAI
from dotenv import load_dotenv

ssl._create_default_https_context = ssl._create_unverified_context
load_dotenv()
#does one specific hallmark also apply for other abstracts?""
target = "Enter Hallmark Target"

json_file_path = "COSMIC_CGC_SAMPLE.json"

pubmed_ids = []

ctd = f"I will provide you an abstract from PubMed. Your job is to check if the abstract is related to '{target}' Think step by step, although you do not have to explain to me your reasoning steps. If the abstract is related, respond with 'yes', and if not, 'no'. Do not tell me anything more than that."


#generates list of pubmed ids that will be scraped
def extract_pubmed_ids(json_file_path, hallmark_name, numData, evn):
    extracted_list = []
    with open(json_file_path, 'r') as file:
        data = json.load(file)
    for index, entry in enumerate(data):
        if entry.get("HALLMARK") == hallmark_name:
            extracted_list.append(entry.get("PUBMED_PMID"))
    for index, entry in enumerate(extracted_list): # data range
        if index % evn == 0: # Within range, systemic random sample collector
            pubmed_ids.append(entry)
    
    lim_pubmed_ids = pubmed_ids[:int(numData)]
    print("length: " + str(len(lim_pubmed_ids)))
    return lim_pubmed_ids
    
abstract_list = []

extracted_list = []
def check_abstract(pubmed_id):
    print(f"Retrieving abstract for PMID {pubmed_id}...")
    url_base = "https://pubmed.ncbi.nlm.nih.gov/"
    url = url_base + str(pubmed_id)
    
    max_attempts = 10 # Reduce the number of attempts
    initial_delay = 1  # Start with a longer delay to give the server more time to recover
    
    for attempt in range(max_attempts):
        try:
            response = requests.get(url, timeout=10)  # Add a timeout for the request
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                abstract_div = soup.find('div', class_='abstract-content')
                if abstract_div:
                    print(f"Abstract retrieved for PMID {pubmed_id}.")
                    return pubmed_id, abstract_div.get_text(strip=True)
                else:
                    print(f"No abstract content found for PMID {pubmed_id}.")
                    return pubmed_id, "No abstract content found"
            else:
                print(f"{pubmed_id}: Attempt {attempt + 1} failed with status code {response.status_code}. Retrying...")
                initial_delay *= 2
        except (ConnectionError, Timeout, ChunkedEncodingError) as e:
            print(f"{pubmed_id}: Attempt {attempt + 1} failed due to a connection error: {e}. Retrying in {initial_delay} seconds...")
        time.sleep(initial_delay)
        initial_delay *= 1.2

def check_hallmark(abstract):
    pmid, abs = abstract
    process_name = current_process().name
    print(f"Checking Abstract {pmid} with process {process_name}")
    
    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4-1106-preview",
        messages=[
            {
                "role": "user",
                "content": ctd + "\n\n" + abs  # Ensure abstract is a string
            }
        ],
        temperature=0,
        max_tokens=4095,
        top_p=0,
        frequency_penalty=0,
        presence_penalty=0
    )

    # Access the content of the response
    result = response.choices[0].message.content
    print(f"extraction {pmid} successful")
    return result

def process_abstracts(pubmed_ids):
    print("Processing abstracts...")
    with Pool(processes=30) as pool:  # Adjust the number of processes according to your system's capability
        results = pool.map(check_abstract, pubmed_ids)
    print("Finished processing abstracts.")
    return results

abstract_list = []

def extract_hallmark(abstract_list):
    with Pool(processes=50) as pool:
        indexed_abstracts = list(abstract_list)
        
        results = pool.map(check_hallmark, indexed_abstracts)
    extracted_list.extend(results)
    return extracted_list
    

if __name__ == "__main__":
    pubmed_ids = extract_pubmed_ids("nx_modified.json", target, 500, 1)
    print(pubmed_ids)
    abstract_list = process_abstracts(pubmed_ids)
    print(abstract_list)
    extract_list = extract_hallmark(abstract_list)
    print(extract_list)
    
    responses = extract_list
    ids = pubmed_ids
    
    no_count = 0
    no_positions = []
    
    for index, response in enumerate(responses):
        if response.lower() == 'no':
            no_count += 1
            no_positions.append(index)
    
    print("Number of 'no' (case-insensitive):", no_count)
    print("Positions of 'no' (case-insensitive):", no_positions)
    
    idpos = []
    for index in no_positions:
        idpos.append(ids[index])
    
    idpos = str(idpos).replace('[',"").replace(']',"").replace("'", "").replace("'","")
    if target == target:
        print(f"Normal accuracy: {no_count}/{len(ids)}")
    else:
        print(f"Different accuracy: {len(ids)-no_count}/{len(ids)}")
    print(f"ids: {idpos}")
