from flask import Flask, request, jsonify
from functools import wraps
from openai import OpenAI
from algoliasearch.search_client import SearchClient
from dotenv import load_dotenv, find_dotenv
import os
import json

# Carregar variáveis de ambiente do arquivo .env
load_dotenv(find_dotenv())

# Configurar a API da OpenAI
client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
)

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
        model="gpt-4o", 
        messages=[
        {
            "role": "system", 
            "content": "Você é um Professor avaliador de redação universitária. Você receberá o tema, redação e um aviso de plágio automático caso o sistema identifique. Você deverá corrigir a redação e, no final, dar uma pontuação de 0 a 10 e comentar o porquê foi dada a pontuação. A saída deverá ser em uma formatação JSON, por exemplo: {'pontuação':'5.5', 'comentario':'abc...'}. " + f"{plagio}\nTema: {tema},\nRedação: {essay}"
          
        }
        ],              
        max_tokens=3000
    )
    corrected_essay = response.choices[0].message.content   
    
    processed_essay = preprocess_text(essay)
    store_processed_text(inscricao, essay, processed_essay, tema)
    
    # Extrair pontuação e comentário da redação corrigida
    pontuacao_comentario = extract_score_and_comment(corrected_essay)
    
    return pontuacao_comentario, corrected_essay

# Função para extrair a pontuação e o comentário da redação corrigida
def extract_score_and_comment(corrected_essay):
    # Esta função precisa ser implementada de acordo com o formato do retorno do OpenAI
    # Exemplo simplificado:
    try:
        result = json.loads(corrected_essay)
        pontuacao = result.get('pontuação', '')
        comentario = result.get('comentario', '')
    except json.JSONDecodeError:
        pontuacao = ''
        comentario = ''
    return {"pontuacao": pontuacao, "comentario": comentario}

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
    
    pontuacao_comentario, corrected_essay = process_essay(inscricao, tema, redacao)
    print(pontuacao_comentario)
    return jsonify({
        "inscricao": inscricao,
        "pontuacao": pontuacao_comentario["pontuacao"],
        "comentario": pontuacao_comentario["comentario"],
        "tema": tema,
        "redacao": redacao
    })

if __name__ == '__main__':
    app.run(debug=True)
