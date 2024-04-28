import json
import requests
import ssl
import time
from bs4 import BeautifulSoup
from requests.exceptions import ConnectionError, ChunkedEncodingError, Timeout
from mysql.connector import connect
from multiprocessing import Pool, current_process
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
ssl._create_default_https_context = ssl._create_unverified_context

hallmark_list = ["Invasion and metastasis", 'change of cellular energetics', 'proliferative signalling', 'genome instability and mutations', 'escaping immune response to cancer',  'cell replicative immortality', 'angiogenesis', 'suppression of growth', 'tumour promoting inflammation', 'escaping programmed cell death', 'clinical impact', 'role in cancer', 'mouse model', 'fusion partner', 'senescence', 'interaction with pathogen', 'global regulation of gene expression', 'types of alteration in cancer', 'impact of mutation on function', 'function summary', 'differentiation and development', 'cell division control']
subcategory_list =['clinical impact', 'role in cancer', 'mouse model', 'fusion partner', 'senescence', 'interaction with pathogen', 'global regulation of gene expression', 'types of alteration in cancer', 'impact of mutation on function', 'function summary', 'differentiation and development', 'cell division control']
json_file_path = "COSMIC_CGC_SAMPLE.json"

def extract_pubmed_ids(json_file_path, numData):
    print("Extracting PubMed IDs...")
    with open(json_file_path, 'r') as file:
        data = json.load(file)
        
    pubmed_ids = [entry.get("PUBMED_PMID") for entry in data][:int(numData)]
    print(f"Extracted {len(pubmed_ids)} PubMed IDs.")
    return pubmed_ids

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

def check_gene(data):
    pmid, abstract = data
    process_name = current_process().name
    print(f"Checking Abstract with process {process_name} for gene extraction")
    client = OpenAI()
    ctd = "I will provide you an abstract from PubMed. Your job is to return the name of the gene that is being discussed in the abstract. Think step by step, although you do not have to explain to me your reasoning steps. Only return the name of the gene, and you must extract two possible genes. First and most importantly, look for phosphorylation: if a protein is phosphorylating, extract the name of the gene that codes for the protein that phosphorylates, and end the analysis. If the abstract mentions a protein, make sure to identify and return the corresponding gene name for that protein. Do not tell me anything other than the name of the gene. If the abstract does not explicitly mention a gene name but discusses a protein, respond with the name of the gene that encodes for the protein mentioned in the context of the abstract. If the role of a protein is the main focus of the abstract, first identify the protein that is the main point of discussion since there could be multiple proteins mentioned in the abstract, and second, extract the name of the gene that codes for the protein. Ensure that you focus on the primary subject of the study, which is often the protein or gene whose function or characteristics are being most extensively explored or characterized in the abstract. Make sure you are returning the name of gene, not protein."
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
    result = response.choices[0].message.content.strip()
    print(f"Gene extraction successful for process {process_name}")
    gene_names = result.split(", ")
    corrected_gene_names = [aliasCheck(gene_name.strip()) for gene_name in gene_names]
    if len(corrected_gene_names) >= 2 and corrected_gene_names[0] == corrected_gene_names[1]:
        corrected_gene_names.pop(1)
    return [pmid] + corrected_gene_names

def process_genes(abstracts):
    print("Extracting gene names...")
    with Pool(processes=30) as pool:
        # Map each abstract to the check_gene function, ensuring the PMID is passed along with the abstract
        results = pool.map(check_gene, abstracts)
    print("Finished extracting gene names.")
    return results

def aliasCheck(gene_name):
    try:
        connection = connect(host="Enter Host Name", user="Enter User Name", password="Enter Password", database="Enter Database Name")
        cursor = connection.cursor()
        query = f"SELECT * FROM 'Database_Name' WHERE Approved_Symbol = '{gene_name}' OR Alias_Symbol = '{gene_name}' OR Previous_Symbol = '{gene_name}';"
        cursor.execute(query)
        records = cursor.fetchall()
        print(f"Records for {gene_name}: {records}")  # Debug output
        if not records:
            return gene_name
        ans = []
        for record in records:
            if record[0] not in ans:
                ans.append(record[0])
        if ans:
            return str(ans[0])
        else:
            return gene_name  # Fallback if ans is unexpectedly empty
    except Exception as e:
        print(f"Error processing {gene_name}: {e}")
        return gene_name  # Fallback in case of error
    finally:
        cursor.close()
        connection.close()

def check_cell_type(data): # Unpack the arguments
    pmid, abstract = data
    process_name = current_process().name
    print(f"Checking Abstract with process {process_name} for cell type extraction")
    client = OpenAI()
    ctd = "I will provide you with an abstract from PubMed. Your job is to return the cell type that is being described in the abstract to be affected. Think step by step, and explain your reasoning steps. Look for two possible cell types that are being discussed. If only one cell type is being discussed, then extract the same cell type twice. If no particular cell type is being discussed, extract '' twice."
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
                "content": f"Read {result1}. Extract the cell type names that were extracted from that text. No descriptions required, only return the cell type names, comma separated."
            }
        ],
        temperature=0,
        max_tokens=4095,
        top_p=0,
        frequency_penalty=0,
        presence_penalty=0
    )
    result2 = response.choices[0].message.content.strip().replace("\n", ", ")
    print(f"Cell type extraction successful for process {process_name}")
    cell_type_names = result2.split(", ")
    if len(cell_type_names) >= 2 and cell_type_names[0] == cell_type_names[1]:
        cell_type_names.pop(1)
    return [pmid] + cell_type_names

def process_cell_type(abstracts):
    print("Extracting cell types...")
    with Pool(processes=30) as pool:
        results = pool.map(check_cell_type, abstracts)
    print("Finished extracting cell types.")
    return results

def check_hallmark(data):
    pmid, abstract, gene_names, cell_types, target = data
    applicable_hallmark = []
    for gene in gene_names:
        for cell in cell_types:       
            print(f"Checking if abstract for PMID {pmid} is related to {target}...")
            
            if target in subcategory_list:
                ctd = f"I will provide you an abstract from PubMed. Your job is to check if the abstract's information can describe {gene}'s effects on {cell} for the topic of {target}. Think step-by-step, break down the abstract into smaller problems, and explain your reasoning process. At the end, make a final decision; if the abstract information can describe the {gene}'s effects on {cell} for the topic of {target} say 'yes.'"
            else:
                ctd = f"I will provide you an abstract from PubMed. Your job is to check if the abstract's information suggest that {gene} has the effect(s) described by the Hallmark {target} on {cell}. Think step-by-step, break down the abstract into smaller problems, and explain your reasoning process. At the end, make a final decision; if abstract's information suggest that {gene} has the effect(s) described by the Hallmark {target} on {cell}, say 'yes.'"
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
            
            result1 = response.choices[0].message.content
            client = OpenAI()
            response = client.chat.completions.create(
                model="gpt-4-1106-preview",
                messages=[
                    {
                        "role": "user",
                        "content": f"Read a response from a GPT: {result1}. Extract 'yes' or 'no' based on what the GPT had answered to the question. Only extract 'yes' or 'no'. No descriptions required."  # Ensure abstract is a string

                    }
                ],
                temperature=0,
                max_tokens=4095,
                top_p=0,
                frequency_penalty=0,
                presence_penalty=0
            )
            result2 = response.choices[0].message.content
            
            if result2.strip().lower() == 'yes':
                applicable_hallmark.append((pmid,abstract,gene,cell,target))
                
    return applicable_hallmark

def process_hallmarks(hallmark_input):
    print("Checking abstracts against hallmarks...")
    
    with Pool(processes=30) as pool:  # Adjust the number of processes according to your system's capability
        results = pool.map(check_hallmark, hallmark_input)
        
    print("Finished checking abstracts against hallmarks.")
    
    rest = []
    for res in results:
        if res != []:
            rest.append(res)
    return rest

def gptdesc(abstract, gene, cell, hallmark):
    ques = f"For gene: {gene}, cell: {cell}, and hallmark: {hallmark}, generate a one or two sentence summary of the abstract's finding, focused on {hallmark}.  Only include sentences of your findings, not things like 'The study demonstrates that,' or 'The study you've described', or any phrases like that."
    print(f"Checking descriptions for hallmark {hallmark}...")
    
    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4-0125-preview",
        messages=[
            {
                "role": "user",
                "content": ques + "\n\n" + abstract
            }
        ],
        temperature=0,
        max_tokens=4095,
        top_p=0,
        frequency_penalty=0,
        presence_penalty=0
    )
    
    description = response.choices[0].message.content.strip()
    return description

def check_desc(data):
    pmid, abstract, gene, cell, hallmark = data[0]
    desclist = []
    if hallmark.lower() in ["cell division control", "clinical impact", "differentiation and development", "function summary", "global regulation of gene expression", "impact of mutation on function", "interaction with pathogen", "mouse model", "types of alteration in cancer"]:
        ctd = f"For gene: {gene}, cell: {cell}, and hallmark: {hallmark} generate a one or two sentence summary of the abstract's finding, focused on {hallmark}.  Only include sentences of your findings, not things like 'The study demonstrates that,' or 'The study you've described', or any phrases like that."
        print(f"Checking descriptions for hallmark {hallmark}...")
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
        description = response.choices[0].message.content.strip()
        desclist.append((pmid,abstract,gene,cell,hallmark,description))
        
    elif hallmark.lower() in ["proliferative signalling", "suppression of growth", "change of cellular energetics"]:
        ques = f"For gene: {gene}, cell: {cell}, and hallmark: {hallmark}, generate a one or two sentence summary of the abstract's finding, focused on how {gene} promotes {hallmark}. Only include sentences of your findings, not things like 'The study demonstrates that,' or 'The study you've described', or any phrases like that."
        print(f"Checking descriptions for hallmark {hallmark}...")
        client = OpenAI()
        response = client.chat.completions.create(
            model="gpt-4-0125-preview",
            messages=[
                {
                    "role": "user",
                    "content": ques + "\n\n" + abstract  # Ensure abstract is a string
                }
            ],
            temperature=0,
            max_tokens=4095,
            top_p=0,
            frequency_penalty=0,
            presence_penalty=0
        )
        description = response.choices[0].message.content.strip()
        desclist.append((pmid,abstract,gene,cell,hallmark,description))
    elif hallmark.lower() in ["angiogenesis", "cell replicative immortality", "escaping immune response to cancer", "genome instability and mutations", "invasion and metastasis", "senescence", "tumour promoting inflammation"]:
        description = gptdesc(abstract,gene,cell,hallmark)
        if description != "":
            desclist.append((pmid,abstract,gene,cell,hallmark,description))
            
    elif hallmark.lower() == "role in cancer":
        ctd = f"Based on the given abstract, determine the role in cancer of gene: {gene} for cell: {cell}. You have three options to choose from, and multiple options may be applicable: A) TSG, B) Oncogene, C) Fusion. If no evidence is presented, extract: D) No evidence. Think step-by-step and explain your reasoning process along the way."
        
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
        
        desc1 = response.choices[0].message.content.strip()
        response = client.chat.completions.create(
            model="gpt-4-0125-preview",
            messages=[
                {
                    "role": "user",
                    "content": ctd + "\n\n" + abstract  # Ensure abstract is a string
                },
                {
                    "role": "assistant",
                    "content": desc1
                },
                {
                    "role": "user",
                    "content": "based on your response above, extract the answer only. For example, if you chose both A) TSG and B) Oncogene, your response shoudl be: 'TSG, Oncogene' If you chose D because there were no evidence, return ''. no descriptions required. Only return the final answer only."
                }
            ],
            temperature=0,
            max_tokens=4095,
            top_p=0,
            frequency_penalty=0,
            presence_penalty=0
        )
        desc = response.choices[0].message.content.strip()
        if desc != '':  
            description = desc
            desclist.append((pmid,abstract,gene,cell,hallmark,description))

    elif hallmark.lower() == "fusion partner":
        ques = f"Extract the fusion partner(s) of gene: {gene} based on the abstract: "
        print(f"Checking descriptions for hallmark {hallmark}...")
        client = OpenAI()
        response = client.chat.completions.create(
            model="gpt-4-0125-preview",
            messages=[
                {
                    "role": "user",
                    "content": ques + "\n\n" + abstract  # Ensure abstract is a string
                }
            ],
            temperature=0,
            max_tokens=4095,
            top_p=0,
            frequency_penalty=0,
            presence_penalty=0
        )
        description1 = response.choices[0].message.content.strip()
        response = client.chat.completions.create(
            model="gpt-4-0125-preview",
            messages=[
                {
                    "role": "user",
                    "content": ques + "\n\n" + abstract  # Ensure abstract is a string
                },
                {
                    "role": "assistant",
                    "content": description1
                },
                {
                    "role": "user",
                    "content": "Extract the fusion partners as a square bracket list. The fusion partners should be enclosed by double quotation marks and separated by commas. Return only the list of fusion partners, nothing more. No descriptions needed."
                }
            ],
            temperature=0,
            max_tokens=4095,
            top_p=0,
            frequency_penalty=0,
            presence_penalty=0
        )
        description = response.choices[0].message.content.strip()
        print("==============================================")
        print(description)
        try:
            description = list(description)
        except Exception as e:
            print(e)
        fp = ""
        if description != "":
            for index, des in enumerate(description):
                if index != len(description) - 1:
                    fp += des + ", "
                    print("==============================================")
                    print(des)
                    print("==============================================")
                else:
                    fp += des
                    print("==============================================")
                    print(des)
                    print("==============================================")
        desclist.append((pmid,abstract,gene,cell,hallmark,fp))
    return desclist

def process_desc(hallmarked_input):
    print("Checking descriptions...")
    
    with Pool(processes=30) as pool:  # Adjust the number of processes according to your system's capability
        results = pool.map(check_desc, hallmarked_input)
        
    rest = []
    for res in results:
        if res != []:
            rest.append(res)
    return rest

if __name__ == "__main__":

    pubmed_ids = extract_pubmed_ids(json_file_path, 2)
    abstracts = process_abstracts(pubmed_ids)
    gene_data = process_genes(abstracts)
    cell_type_data = process_cell_type(abstracts)
    
    hallmark_prep = []
    hallmark_input = []
    for index, abstract in enumerate(abstracts):
        listed_abstract = list(abstract)
        gene_tuple = tuple(gene_data[index][1:])
        cell_type_tuple = tuple(cell_type_data[index][1:])
        listed_abstract.append(gene_tuple)
        listed_abstract.append(cell_type_tuple)
        hallmark_prep.append(listed_abstract)
    
    for hallmark in hallmark_list:  
        for prep in hallmark_prep:
            prep_copy = list(prep)
            prep_copy.append(hallmark)
            if tuple(prep_copy) not in hallmark_input:
                hallmark_input.append(tuple(prep_copy))

    hallmarked_input = process_hallmarks(hallmark_input)
    output = process_desc(hallmarked_input)
    print(output)

    records = []
    for i in range(len(output)):
        
        record_dict = {
            "GENE_NAME": output[i][0][2],
            "CELL_TYPE": output[i][0][3],
            "PUBMED_PMID": output[i][0][0],
            "HALLMARK": output[i][0][4],
            "DESCRIPTION": output[i][0][5]
        }
    
        
        records.append(record_dict)
    with open('final_results.json', 'w') as json_file:
        json.dump(records, json_file, indent=2)
        