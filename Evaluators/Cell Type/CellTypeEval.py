import json
import requests
import ssl
import time
import re
from requests.exceptions import ConnectionError, ChunkedEncodingError, Timeout
from openai import OpenAI
from bs4 import BeautifulSoup
from multiprocessing import Pool
from dotenv import load_dotenv

load_dotenv()
ssl._create_default_https_context = ssl._create_unverified_context

json_file_path = "COSMIC_GCG_SAMPLE.json"

def extract_pubmed_ids(json_file_path, numData, step):
    print("Extracting PubMed IDs...")
    with open(json_file_path, 'r') as file:
        data = json.load(file)
    
    filtered_data = [entry for entry in data if entry.get("HALLMARK") not in [
        "cell division control", "clinical impact", "differentiation and development", 
        "function summary", "fusion partner", "global regulation of gene expression", 
        "impact of mutation on function", "interaction with pathogen", "mouse model", 
        "types of alteration in cancer", "proliferative signalling", "suppression of growth"]]
    
    filtered_data = [entry for entry in data if entry.get("HALLMARK") in [
        f"{hallmarkt}"] and entry.get("CELL_TYPE") != ""]

    # Extract every nth entry up to numData
    selected_data = [filtered_data[i] for i in range(0, len(filtered_data), step)][:numData]
    
    pubmed_ids = [entry.get("PUBMED_PMID") for entry in selected_data]
    hallmarks = [entry.get("HALLMARK") for entry in selected_data]
    
    print(f"Extracted {len(pubmed_ids)} PubMed IDs.")
    return pubmed_ids, hallmarks

def extract_impactlist(json_file_path, numData, step):
    with open(json_file_path, 'r') as file:
        data = json.load(file)
    
    filtered_data = [entry for entry in data if entry.get("HALLMARK") not in [
        "cell division control", "clinical impact", "differentiation and development", 
        "function summary", "fusion partner", "global regulation of gene expression", 
        "impact of mutation on function", "interaction with pathogen", "mouse model", 
        "types of alteration in cancer", "proliferative signalling", "suppression of growth"]]\
    
    filtered_data = [entry for entry in data if entry.get("HALLMARK") in [
       f"{hallmarkt}"] and entry.get("CELL_TYPE") != ""]
    
    
    # Extract every nth entry up to numData
    selected_data = [filtered_data[i] for i in range(0, len(filtered_data), step)][:numData]
    
    impactlist = [entry.get("CELL_TYPE") for entry in selected_data]
    return impactlist

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

    
def process_abstracts(pubmed_ids):
    print("Processing abstracts...")
    with Pool(processes=50) as pool:
        results = pool.map(check_abstract, pubmed_ids)
    print("Finished processing abstracts.")
    return results

def check_line(data):
    hallmark, abstract = data
    if hallmark.lower() in "function summary":
        type = ""
    elif hallmark != "function summary":
        ctd = "I will provide you with an abstract from PubMed. Your job is to extract cancer cell type discussed in relation to the given abstract: the specific types of cells or tissues that are associated with a particular disease or condition. Think step-by-step and explain your reasoning process. Look for two best cell types. If you are sure that only one cell type is applicable, only return that cell type."
        client = OpenAI()
        response = client.chat.completions.create(
            model="gpt-4-0125-preview",
            messages=[
                {
                    "role": "user",
                    "content": ctd + "\n\n" + abstract  # Ensure abstract is a string
                }
            ],
            temperature=0,
            max_tokens=4095,
            top_p=0,
            frequency_penalty=0,
            presence_penalty=0
        )
        result1 = response.choices[0].message.content.strip()
        print(result1)
        client = OpenAI()
        response = client.chat.completions.create(
            model="gpt-4-0125-preview",
            messages=[
                {
                    "role": "user",
                    "content": f"A GPT responded: {result1} for a question asking to identify cell types mentioned in PubMed abstract. Extract comma separated list of cell types from GPT response. No descriptions required, extract only the cell types."
                }
            ],
            temperature=0,
            max_tokens=4095,
            top_p=0,
            frequency_penalty=0,
            presence_penalty=0
        )
        result2 = response.choices[0].message.content.strip()
        type = result2
    else:
        print('Error! Invalid Hallmark')
        type = "Invalid Hallmark!!!!"
    print(type)
    return type

def prepare_data_for_multiprocessing(hallmarks, abstracts):
    # Ensure we're using the full abstract text, which is the second element in each tuple
    combined_data = list(zip(hallmarks, [abstract[1] for abstract in abstracts]))
    return combined_data

def process_data_with_multiprocessing(combined_data):
    with Pool(processes=50) as pool:
        impacts = pool.map(check_line, combined_data)
    return impacts

def process_item(item):
    PMID, hallmark, answer, extracted_result = item
    if extracted_result != answer and extracted_result != '':
        client = OpenAI()  # Update this with the correct way to initialize your OpenAI client
        response = client.chat.completions.create(  # Update this call according to the actual OpenAI Python client API
            model="gpt-4-0125-preview",
            messages=[
                {
                    "role": "user",
                    "content": f"Using your medical knowledge and reasoning skills, check if the any of the cells in list: {extracted_result.replace(' cells', '')} are equal to, are subsets of, or (broadly) includes the cells in list : {answer.lower().replace(' and ', ', ')}, or vice versa. There could be only one element in the list, if so, check if the smaller list is a subset of the bigger list. If both lists have only one element, check if they are referring to same cell type. The two lists do not have to be exactly equal, but at least one element from both lists should be closely related. \n\nRespond 'Yes', if it does, and 'No' if it does not. The lists of cell types that are being compared may be in a different format such as uppercase/lowercase and spacing. Be careful with those."                }
            ],
            temperature=0,
            max_tokens=4095,
            top_p=0,
            frequency_penalty=0,
            presence_penalty=0
        )
        result = response.choices[0].message.content.strip().lower()
        result = re.sub(r'[^a-zA-Z0-9]', '', result)
        if result == "yes":
            return (PMID, hallmark, answer, extracted_result)
        else:
            print(result + " " + PMID)
    return None

def list_check(errorlist, goodlist):
    with Pool(processes=50) as pool:  # Adjust the number of processes according to your machine's capabilities
        results = pool.map(process_item, errorlist)
        
    for result in filter(None, results):
        errorlist.remove(result)  # Be careful with directly removing items from the list you're iterating over
        goodlist.append(result)


if __name__ == "__main__":
    
    hallmarkt = str(input("Enter target hallmark: "))
    hallmarkt = hallmarkt.lower()
    
    pubmed_ids, hallmarks = extract_pubmed_ids(json_file_path, 100, 1)
    print(pubmed_ids)
    print(hallmarks)
    impactlist = extract_impactlist(json_file_path, 100, 1)
    abstracts = process_abstracts(pubmed_ids)
    
    # Debugging: Print the first few abstracts to verify their content

    
    combined_data = prepare_data_for_multiprocessing(hallmarks, abstracts)
    
    # Debugging: Print combined_data to verify its structure
    
    gen_impacts = process_data_with_multiprocessing(combined_data)
    final_output = list(zip(pubmed_ids, hallmarks, gen_impacts))

    counter = 0
    errorlist = []
    goodlist = []
    for PMID, hallmark, impact in final_output:
        if impact.lower() == impactlist[counter].lower():
            goodlist.append((PMID, hallmark, impactlist[counter].lower(), impact))
            counter += 1
        else:
            errorlist.append((PMID, hallmark, impactlist[counter].lower(), impact))
            counter += 1 
    list_check(errorlist, goodlist)
    print("==================================")
    print(len(errorlist), errorlist)
    print("==================================")
    print(len(goodlist), goodlist)
    
            