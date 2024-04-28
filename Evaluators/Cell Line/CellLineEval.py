import json
import requests
import ssl
import time
from openai import OpenAI
from bs4 import BeautifulSoup
from multiprocessing import Pool
from dotenv import load_dotenv

load_dotenv()
ssl._create_default_https_context = ssl._create_unverified_context

json_file_path = "COSMIC_CGC_SAMPLE.json"


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
        f"{hallmarkt}"] and entry.get("CELL_LINE") != ""]

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
        f"{hallmarkt}"] and entry.get("CELL_LINE") != ""]
    
    
    # Extract every nth entry up to numData
    selected_data = [filtered_data[i] for i in range(0, len(filtered_data), step)][:numData]
    
    impactlist = [entry.get("CELL_LINE") for entry in selected_data]
    return impactlist

def check_abstract(pubmed_id):
    print(f"Retrieving abstract for PMID {pubmed_id}...")
    url_base = "https://pubmed.ncbi.nlm.nih.gov/"
    url = url_base + str(pubmed_id)
    
    attempts = 10  # Number of attempts
    delay = 0.1  # Delay in seconds between attempts
    
    for attempt in range(attempts):
        response = requests.get(url)
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
            print(f"Attempt {attempt + 1} failed to retrieve content for PMID {pubmed_id}. Retrying in {delay} seconds...")
            time.sleep(delay)  # Wait for a few seconds before retrying
    
    # After all attempts
    print(f"Failed to retrieve content for PMID {pubmed_id} after {attempts} attempts.")
    return pubmed_id, "Failed to retrieve content after multiple attempts"
    
def process_abstracts(pubmed_ids):
    print("Processing abstracts...")
    with Pool(processes=30) as pool:
        results = pool.map(check_abstract, pubmed_ids)
    print("Finished processing abstracts.")
    return results

def check_line(data):
    hallmark, abstract = data
    if hallmark.lower() in ["function summary", "role in cancer", "fusion partner", "mouse model", "types of alteration in cancer", "clinical impact"]:
        line = ""
    elif hallmark.lower() not in ["function summary", "role in cancer", "fusion partner", "mouse model", "types of alteration in cancer", "clinical impact"]:
        client = OpenAI()
        ctd = "I will provide you with an abstract from PubMed. Your job is to extract cell lines: specific types of cells that are derived from a particular tissue or organism and can be grown and maintained in a laboratory setting. If multiple cell lines are applicable, return a comma separated list of those. If the abstract mentions no cell lines, use your scientific knowledge and reasoning skills to come up with the best guess for three possible cell lines related considering the whole abstract, comma separated. Only return your answer. No descriptions required."

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
        line = response.choices[0].message.content.strip()
    else:
        print('Error! Invalid Hallmark')
        line = "Invalid Hallmark!!!!"
    
    return line

def prepare_data_for_multiprocessing(hallmarks, abstracts):
    # Ensure we're using the full abstract text, which is the second element in each tuple
    combined_data = list(zip(hallmarks, [abstract[1] for abstract in abstracts]))
    return combined_data

def process_data_with_multiprocessing(combined_data):
    with Pool(processes=30) as pool:
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
                    "content": f"Here is the first list of cells: {extracted_result}\n\nHere is the second list of cells: {answer.lower().replace(' and ', ', ')}\n\nUsing your medical knowledge, please determine if any of the object(s) in the first list is equal to, is a subset of, or (broadly) includes the second list. Respond 'Yes', if it does, and 'No' if it does not. The objects in the first and second list may be in a different format such as uppercase/lowercase and spacing. Be careful with those."
                }
            ],
            temperature=0,
            max_tokens=4095,
            top_p=0,
            frequency_penalty=0,
            presence_penalty=0
        )
        result = response.choices[0].message.content.strip()
        if result == "Yes":
            return (PMID, hallmark, answer, extracted_result)
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
    pubmed_ids, hallmarks = extract_pubmed_ids(json_file_path, 300, 1)
    print(pubmed_ids)
    print(hallmarks)
    impactlist = extract_impactlist(json_file_path, 300, 1)
    abstracts = process_abstracts(pubmed_ids)
    
    combined_data = prepare_data_for_multiprocessing(hallmarks, abstracts)
    
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
    
            