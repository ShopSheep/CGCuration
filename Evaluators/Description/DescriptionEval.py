import json
from dotenv import load_dotenv
from openai import OpenAI
from mysql.connector import connect

load_dotenv()


with open('final_results.json', 'r') as file:
    data1 = json.load(file)

with open('COSMIC_CGC_SAMPLE', 'r') as file:
    data2 = json.load(file)
    
def aliasCheck(gene_name):
    connection = connect(host = "localhost", user = "root", password = "rohjy0329", database = "genomeinsight") 
    cursor = connection.cursor()
    cursor.execute(f"SELECT * FROM genomeinsight.genealias WHERE Approved_Symbol = '{gene_name}' OR Alias_Symbol = '{gene_name}' OR Previous_Symbol = '{gene_name}';")
    records = cursor.fetchall()
    if records == []:
        return gene_name
    ans = []
    for record in records:
        if record[0] not in ans:
            ans.append(record[0])
    return str(ans[0])

numCompare = 0
correct = 0

for obj in data1:
    PMIDTarget = obj.get("PUBMED_PMID")
    GeneTarget = aliasCheck(obj.get("GENE_NAME"))
    HallmarkTarget = obj.get("HALLMARK").lower()
    Desc1 = obj.get("DESCRIPTION")
    for comp in data2:
        if comp.get("PUBMED_PMID") == PMIDTarget and aliasCheck(comp.get("GENE_NAME")) == GeneTarget and comp.get("HALLMARK").lower() == HallmarkTarget:
            numCompare += 1
            if HallmarkTarget == "role in cancer":
                if Desc1.lower() == comp.get("DESCRIPTION").lower():
                    correct += 1
            else:
                client = OpenAI()
                response = client.chat.completions.create(
                    model="gpt-4-0125-preview",
                    messages=[
                        {
                            "role": "user",
                            "content": f"Compare: description 1: {Desc1} and descripion 2: {comp.get('DESCRIPTION')}. If descripion 1 conveys the same information, or same information and additional information compared to description 2, return 'True', and if not, return 'False.' Think step-by-step."
                        }
                    ],
                    temperature=0,
                    max_tokens=4095,
                    top_p=0,
                    frequency_penalty=0,
                    presence_penalty=0
                )
                resp = response.choices[0].message.content.strip()
                response = client.chat.completions.create(
                    model="gpt-4-0125-preview",
                    messages=[
                        {
                            "role": "user",
                            "content": f"Read {resp} and return 'True' or 'False' based on the given text. Only return True or False, case sensitive. No other information required."
                        }
                    ],
                    temperature=0,
                    max_tokens=4095,
                    top_p=0,
                    frequency_penalty=0,
                    presence_penalty=0
                )
                result = response.choices[0].message.content.strip()
                if result == "True":
                    correct += 1
                else:
                    print(result)
                    print(PMIDTarget)
                    print(HallmarkTarget)
                    print(Desc1)
                    print(comp.get("DESCRIPTION"))

print(f"Accuracy: {correct}/{numCompare}")
        
    