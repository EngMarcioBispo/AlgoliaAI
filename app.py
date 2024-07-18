from flask import Flask, request, jsonify
from functools import wraps
from openai import OpenAI
from algoliasearch.search_client import SearchClient
from dotenv import load_dotenv, find_dotenv
import os
import re

# Carregar variáveis de ambiente do arquivo .env
load_dotenv(find_dotenv())

# Configurar a API da OpenAI
client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
)

# Função para extrair a pontuação usando regex
def extrair_pontuacao(data):
    match = re.search(r"#pontuacao=\*\*(\d+(\.\d+)?)\*\*", data)
    if match:
        return match.group(1)
    return None

# Função para extrair o comentário usando regex
def extrair_comentario(data):
    match = re.search(r"#comentario=\*\*(.+?)\*\*", data)
    if match:
        return match.group(1)
    return None

# Configurar o cliente Algolia
algolia_client = SearchClient.create(os.getenv('ALGOLIA_ID'), os.getenv('ALGOLIA_API'))
index = algolia_client.init_index('formatted_doc')

# Função para pré-processar o texto
def preprocess_text(text):
    return text.lower()

# Função para verificar plágio no Algolia
def check_plagiarism(processed_text):
    if len(processed_text) > 512:
        processed_text = processed_text[:512]
    
    search_results = index.search(processed_text)
    return len(search_results['hits']) > 0

# Função para armazenar a redação processada no Algolia
def store_processed_text(inscricao, original_text, processed_text, tema):
    record = {
        'inscricao': inscricao,
        'redacao': original_text,
        'tema': tema
    }
    index.save_object(record, {'autoGenerateObjectIDIfNotExist': True})

# Função para processar a redação
def process_essay(inscricao, tema, essay):
    paragraphs = essay.split('\n\n')
    
    plagiarism_detected = False
    plagiarism_paragraphs = []

    for i, paragraph in enumerate(paragraphs):
        sentences = paragraph.split('. ')
        for sentence in sentences:
            processed_sentence = preprocess_text(sentence)
            if check_plagiarism(processed_sentence):
                plagiarism_detected = True
                plagiarism_paragraphs.append(i + 1)
                break

    plagio = f"Plágio detectado nos parágrafos: {', '.join(map(str, plagiarism_paragraphs))}" if plagiarism_detected else ""

    response = client.chat.completions.create(
        model="gpt-4", 
        messages=[
            {
                "role": "system", 
                "content": "Você é um Professor avaliador de redação universitária. Você receberá o tema, redação e um aviso de plágio automático caso o sistema identifique. Você deverá corrigir a redação e, no final, dar uma pontuação de 0 a 10 e comentar o porquê foi dada a pontuação. A saída deverá ser em uma formatação exemplo: '#pontuacao=**5.5**; #comentario=**abc**'" + f"{plagio}\nTema: {tema},\nRedação: {essay}"
            }
        ],        
        max_tokens=3000
    )
    corrected_essay = response.choices[0].message.content    
    
    return corrected_essay

# Função para extrair a pontuação e o comentário da redação corrigida

# Configurar Flask
app = Flask(__name__)

# Decorator para verificar token
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('x-access-token')
        if not token or token != os.getenv('API_TOKEN'):
            return jsonify({'message': 'Token is missing or invalid!'}), 403
        return f(*args, **kwargs)
    return decorated

@app.route('/process_essay', methods=['POST'])
@token_required
def process_essay_endpoint():
    data = request.get_json()
    inscricao = data.get('inscricao')
    tema = data.get('tema')
    redacao = data.get('redacao')
    
    if not inscricao or not tema or not redacao:
        return jsonify({'message': 'Missing required fields'}), 400
    
    data = process_essay(inscricao, tema, redacao)  
   
    return jsonify({
        "inscricao": inscricao,
        "pontuacao": extrair_pontuacao(data),
        "comentario": extrair_comentario(data),
        "tema": tema,
        "redacao": redacao
    })

if __name__ == '__main__':
    app.run(debug=True)
