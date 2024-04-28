# COSMIC Cancer Genome Census Data Curation using GPT-4

- Using our extraction mechanism, GPT-4 can curate COSMIC CGC dataset with 79% accuracy.
- We utilized Zero-shot Chain-Of-Thought (CoT) approach, and Retrieval-Augmented Generation (RAG) to automate the curation process for COSMIC CGC Dataset.

Contact: David Roh, [Youngmok Jung](https://quito418.github.io/quito418/)

Email: shwlsdud16@icloud.com, youngmok.jung@inocras.com

---

## Contents
* [Extraction Accuracy](#extraction-accuracy)
* [Notes](#notes)
---
## Extraction Accuracy
- We have evaluated GPT-4's extraction performance for the following categories in COSMIC CGC data: Gene Name, Cell Type, Hallmark, and Descripton.
- For Gene Name, Cell Type, and Hallmark extractions, we utilized Retrieval-Augmented Generation by providing the LLM with PubMed abstracts.
- For Gene Name and Hallmark evaluations, we used text comparison.
- For Cell Type and Description evaluations, we used semantic comparison using GPT-4.
- Gene Name extraction showed 93% accuracy using 0-Shot CoT approach.
- Cell Type extraction showed 92.4% accuracy using 0-shot CoT approach.
- Hallmark extraction showed 96.7% accuracy using 0-shot CoT approach.
- Descripton extraction showed 92.7% accuracy using 0-shot approach.
---
## Notes
- We used python virtual environments during the production. To run this code, you will have to store your OpenAI API key in .env file. Use python-dotenv.
- We used the gene alias data from genenames.org to construct mySQL database to convert extracted gene symbols to up-to-date versions. To run this code, you will have to construct a mySQL dataset using geneAlias.csv and make necessary adjustments. Source: https://www.genenames.org/download/custom/
