from mysql.connector import connect
import json
import requests
import time
from bs4 import BeautifulSoup
from openai import OpenAI
from dotenv import load_dotenv
from requests.exceptions import ConnectionError, ChunkedEncodingError, Timeout
import ssl
from multiprocessing import Pool, current_process

ssl._create_default_https_context = ssl._create_unverified_context
load_dotenv()

ctd = "I will provide you an abstract from PubMed. Your job is to return the name of the gene that is being discussed in the abstract. Think step by step, although you do not have to explain to me your reasoning steps. Only return the name of the gene, and you must extract two possible genes. First and most importantly, look for phosphorylation: if a protein is phosphorylating, extract the name of the gene that codes for the protein that phosphorylates, and end the analysis. If the abstract mentions a protein, make sure to identify and return the corresponding gene name for that protein. Do not tell me anything other than the name of the gene. If the abstract does not explicitly mention a gene name but discusses a protein, respond with the name of the gene that encodes for the protein mentioned in the context of the abstract. If the role of a protein is the main focus of the abstract, first identify the protein that is the main point of discussion since there could be multiple proteins mentioned in the abstract, and second, extract the name of the gene that codes for the protein. Ensure that you focus on the primary subject of the study, which is often the protein or gene whose function or characteristics are being most extensively explored or characterized in the abstract. Make sure you are returning the name of gene, not protein."
pubmed_ids = []
gene_ans = []
def extract_infos(json_file_path, numData, evn):
    pmid_list = []
    gene_list = []
    
    with open(json_file_path, 'r') as file:
        data = json.load(file)
    for index, entry in enumerate(data):
        pmid_list.append(entry.get("PUBMED_PMID"))
        gene_list.append(entry.get("GENE_NAME"))
    for index, entry in enumerate(pmid_list[0:]): # data range
        if index % evn == 0: # Within range, systemic random sample collector
            pubmed_ids.append(entry)
    for index, entry in enumerate(gene_list[0:]):
        if index % evn == 0:
            gene_ans.append(entry)
    lim_pubmed_ids = pubmed_ids[:int(numData)]
    lim_gene_ans = gene_ans[:int(numData)]
    print("length: " + str(len(lim_pubmed_ids)))
    return lim_pubmed_ids, lim_gene_ans

def check_abstract(pubmed_id):
    print(f"Retrieving abstract for PMID {pubmed_id}...")
    url_base = "https://pubmed.ncbi.nlm.nih.gov/"
    url = url_base + str(pubmed_id)
    
    max_attempts = 10
    initial_delay = 1
    
    for attempt in range(max_attempts):
        try:
            response = requests.get(url, timeout=10)
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
    with Pool(processes=30) as pool:
        results = pool.map(check_abstract, pubmed_ids)
    print("Finished processing abstracts.")
    return results

def aliasCheck(gene_name):
    connection = connect(host = "Enter Host Name", user = "Enter Username", password = "Enter Password", database = "Enter Database Name") 

    cursor = connection.cursor()

    cursor.execute(f"SELECT * FROM 'Database_Name' WHERE Approved_Symbol = '{gene_name}' OR Alias_Symbol = '{gene_name}' OR Previous_Symbol = '{gene_name}';")
    records = cursor.fetchall()
    if records == []:
        return gene_name
    ans = []
    for record in records:
        if record[0] not in ans:
            ans.append(record[0])
    
    return str(ans[0])

def check_gene(data):
    pmid, abstract = data
    process_name = current_process().name
    print(f"Checking Abstract with process {process_name} for gene extraction")
    client = OpenAI()
    ctd = "I will provide you an abstract from PubMed. Your job is to return the name of the gene that is being discussed in the abstract. Think step by step, and explain your reasoning steps. Look for two possible genes that are being discussed. First and most importantly, look for phosphorylation: if a protein is phosphorylating, extract the name of the gene that codes for the protein that phosphorylates, and end the analysis. If the abstract mentions a protein but not gene, identify and return the corresponding gene name for that protein. If the abstract does not explicitly mention a gene name but discusses a protein, respond with the name of the gene that encodes for the protein mentioned in the context of the abstract. If the role of a protein is the main focus of the abstract, first identify the protein that is the main point of discussion since there could be multiple proteins mentioned in the abstract, and second, extract the name of the gene that codes for the protein. Ensure that you focus on the primary subject of the study, which is often the protein or gene whose function or characteristics are being most extensively explored or characterized in the abstract. Make sure you are returning the name of gene, not protein. Try to return the symbol for the extracted gene names, not the outdated ones."
    response = client.chat.completions.create(
        model="gpt-4-0125-preview",
        messages=[
            {
                "role": "user",
                "content": ctd + "\n\n" + abstract
            }
        ],
        temperature=0,
        max_tokens=4095,
        top_p=0,
        frequency_penalty=0,
        presence_penalty=0
    )
    result1 = response.choices[0].message.content.strip()
    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4-0125-preview",
        messages=[
            {
                "role": "user",
                "content": f"Read {result1}. Extract the gene symbols that were extracted from that text. No descriptions required, only return the gene symbols, comma separated."
            }
        ],
        temperature=0,
        max_tokens=4095,
        top_p=0,
        frequency_penalty=0,
        presence_penalty=0
    )
    result2 = response.choices[0].message.content.strip().replace("\n", ", ")
    return result2

extracted_list = []
def process_genes(abstracts):
    print("Extracting gene names...")
    with Pool(processes=30) as pool:
        # Map each abstract to the check_gene function, ensuring the PMID is passed along with the abstract
        results = pool.map(check_gene, abstracts)
    print("Finished extracting gene names.")
    return results

def check_alias(gene_names):
    with Pool(processes=50) as pool:
        # Flatten the list of gene names, splitting by '\n' and removing empty strings
        flattened_gene_names = [name for sublist in gene_names for name in sublist.split('\n') if name]
        # Remove duplicates to avoid redundant checks
        unique_gene_names = list(set(flattened_gene_names))
        # Check aliases for each unique gene name
        results = pool.map(aliasCheck, unique_gene_names)
        # Create a dictionary for quick lookup
        alias_dict = {name: result for name, result in zip(unique_gene_names, results)}
        # Map the original gene names to their aliases using the dictionary
        checked_aliases = [[alias_dict.get(name) or name for name in sublist.split('\n')] for sublist in gene_names]
    return checked_aliases

def compare_genes(expected_genes, actual_genes):
    differences = []
    for index, (expected_list, actual_list) in enumerate(zip(expected_genes, actual_genes)):
        # Flatten the actual genes list and remove duplicates
        actual_flat = set(name for name in actual_list)
        # Flatten the expected genes list and remove duplicates
        expected_flat = set(name for name in expected_list)
        # Check if there's a mismatch between expected and actual genes
        if not expected_flat.issubset(actual_flat):
            differences.append((f'index: {index}', pubmed_ids[index], expected_list[0], actual_list))
    return differences
            
if __name__ == "__main__":
    pubmed_ids , gene_ans = extract_infos("COSMIC_GCG_SAMPLE.json", 200, 10)
    print(pubmed_ids)
    gene_answer = check_alias(gene_ans)
    print(gene_answer)
    abstract_list = process_abstracts(pubmed_ids)
    print(abstract_list)
    extract_list = process_genes(abstract_list)

    gene_response = check_alias(extract_list)
    print(gene_response)
    correct = [(pubmed_ids[index], item1) for index, item1 in enumerate(zip(gene_answer))]
    dupNum = 0
    dupNum = 0

# Create a set to keep track of unique pairs
    same_elements_count = 0

# Iterate over the list of gene pairs
    for anslist in gene_response:
        # Check if all elements in the sublist are the same
        if all(element == anslist[0] for element in anslist):
            # If they are, increment the counter
            same_elements_count += 1
    
    print(f"Number of duplicates: {same_elements_count}/{len(gene_answer)}")
    
    differences = compare_genes(gene_answer, gene_response)
    
    print("Differences (ordered by index):", differences)
    print(f"error rate: {len(differences)}/{len(gene_answer)}")
    