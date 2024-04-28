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

load_dotenv()
ssl._create_default_https_context = ssl._create_unverified_context

json_file_path = "COSMIC_CGC_SAMPLE.json"

hallm = "cell replicative immortality"
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
        hallm]]

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
        "types of alteration in cancer", "proliferative signalling", "suppression of growth"]]
    
    filtered_data = [entry for entry in data if entry.get("HALLMARK") in [
        hallm]]
    
    
    # Extract every nth entry up to numData
    selected_data = [filtered_data[i] for i in range(0, len(filtered_data), step)][:numData]
    
    impactlist = [entry.get("IMPACT") for entry in selected_data]

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
    with Pool(processes=30) as pool:  # Adjust the number of processes according to your system's capability
        results = pool.map(check_abstract, pubmed_ids)
    print("Finished processing abstracts.")
    return results

def check_impact(data):
    hallmark, abstract = data
    # Initialize OpenAI client outside of the if-else structure to avoid redundancy


    # Placeholder for your logic to determine the impact
    if hallmark.lower() in ["cell division control", "clinical impact", "differentiation and development", "function summary", "fusion partner", "global regulation of gene expression", "impact of mutation on function", "interaction with pathogen", "mouse model", "types of alteration in cancer"]:
        impact = ""
    elif hallmark.lower() in ["proliferative signalling", "suppression of growth", "change of cellular energetics"]:
        impact = "promotes"
    elif hallmark.lower() in ["angiogenesis", "cell replicative immortality", "escaping immune response to cancer", "genome instability and mutations", "invasion and metastasis", "senescence", "tumour promoting inflammation"]:
        client = OpenAI()
        print("Hallmark: ", hallmark)
        ctd = "I will provide you an abstract from PubMed. Please determine if the wildtype gene product of the gene mentioned in the given abstract deregulates cellular energetics. Deregulated cellular energetics mean that Cancer cells are reprogramming their energy metabolism to support their rapid growth and division, often through increased glucose uptake and fermentation to lactate (even in the presence of oxygen, known as the Warburg effect).\n\nFirst, identify the wild type gene product.\n\nSecond, Think step-by-step, break down into smaller problems, and explain your reasonings.\n\nLast, make your decision - Your choices are: A) Promotes -  if the wild type gene product causes deregulation, B) Suppresses - if the wild type gene product causes proper regulation, and C) Promotes and Suppresses - if has both effects Return your final response in letters A, B, C"
        response = client.chat.completions.create(
            model="gpt-4-0125-preview",
            messages=[
                {
                "role": "user",
                "content": ctd + "\n\n" + abstract
                },
            ],
            temperature=0,
            max_tokens=4095,
            top_p=0,
            frequency_penalty=0,
            presence_penalty=0
        )
        impact1 = response.choices[0].message.content.strip()
        client = OpenAI()
        response = client.chat.completions.create(
            model="gpt-4-0125-preview",
            messages=[
                {
                    "role": "user",
                    "content": f"Read this dialogue between a user and GPT-4. Question: {ctd}, Answer: {impact1}. The GPT's response is in letters, either A, B, C, or D. Extract what the GPT had responded; 'promotes' if A, 'suppresses' if B, 'promotes and suppresses' if C, and '' if D. You are only returning 'promotes' , 'suppresses', 'promotes and suppresses' depending on GPT's response. No descriptions required. Do not include the letters either."
                }
            ],
            temperature=0,
            max_tokens=4095,
            top_p=0,
            frequency_penalty=0,
            presence_penalty=0
        )
        impact = response.choices[0].message.content.strip()
        print(impact)
    elif hallmark.lower() == "escaping programmed cell death":
        client = OpenAI()
        ctd = f"I will provide you with an abstract from PubMed. First, please determine if the wildtype protein related to the gene of interest promotes or suppresses escaping programmed cell death. Extract 'promotes' if promotes, and 'suppresses' if suppresses, and 'promotes and suppresses' if both. Only return your answer. Think for both implicit and explicit possibilities. Extract '' if nothing is applicable. Be thoughtful. If the protein increases the escaping of programmed cell death, then it would be promoting. Do not check if the protein promotes the process of programmed cell death. You are checking for the opposite. If the protein decreases the escaping of programmed cell death, then it would be suppressing. No descriptions required."
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
        impact = response.choices[0].message.content.strip()
    elif hallmark.lower() == "role in cancer":
        client = OpenAI()
        ctd = f"I will provide you with an abstract from PubMed. Your job is to determine the role of gene mentioned in the abstract. - 'oncogene' if hyperactivity of the gene drives the transformation, 'fusion' the gene is known to be involved in oncogenic fusions. 'TSG' loss of gene function drives the transformation. Only return your answer. Extract '' if nothing is applicable. No descriptions required."
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
        impact = response.choices[0].message.content.strip()
    else:
        print('Error! Invalid Hallmark')
        impact = "Invalid Hallmark!!!!"
    
    return impact

def prepare_data_for_multiprocessing(hallmarks, abstracts):
    # Ensure we're using the full abstract text, which is the second element in each tuple
    combined_data = list(zip(hallmarks, [abstract[1] for abstract in abstracts]))
    return combined_data

def process_data_with_multiprocessing(combined_data):
    print("processing impacts")
    with Pool(processes=30) as pool:
        impacts = pool.map(check_impact, combined_data)
    return impacts

if __name__ == "__main__":
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
    print("==================================")
    print(len(errorlist), errorlist)
    print("==================================")
    print(len(goodlist), goodlist)
    
    