import json

path = 'workspace/EX-Port639-F2-2024_net/questoes_review.json'
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

for q in data:
    qid = q['id_item']
    q['reviewed'] = True
    
    if qid in ['I-ctx2', 'I-A-1', 'I-A-2', 'I-A-3', 'I-C-7']:
        q['tema'] = 'Educação Literária — Romance'
        q['subtema'] = 'Eça de Queirós, «A Cidade e as Serras» — A civilização'
        q['descricao_breve'] = 'Interpretação e análise do texto'
    elif qid in ['I-ctx3', 'I-B-4', 'I-B-5', 'I-B-6']:
        q['tema'] = 'Educação Literária — Poesia do século XX'
        q['subtema'] = 'Fernando Pessoa, heterónimo Ricardo Reis — Ideal de vida'
        q['descricao_breve'] = 'Interpretação e análise poética'
    elif qid == 'I-ctx1':
        q['tema'] = 'Educação Literária'
        q['subtema'] = 'Instrução do grupo'
        q['descricao_breve'] = 'Instrução'
    elif qid in ['II-ctx1', 'II-1', 'II-2', 'II-3', 'II-4']:
        q['tema'] = 'Leitura — Texto de opinião'
        q['subtema'] = 'A gestão do tempo e o inacabado'
        q['descricao_breve'] = 'Interpretação de texto'
    elif qid == 'II-5':
        q['tema'] = 'Gramática — Valor modal'
        q['subtema'] = 'Modalidade'
        q['descricao_breve'] = 'Identificação de modalidade'
    elif qid == 'II-6':
        q['tema'] = 'Gramática — Funções sintáticas'
        q['subtema'] = 'Modificador e Complemento'
        q['descricao_breve'] = 'Identificação de funções sintáticas'
    elif qid == 'II-7':
        q['tema'] = 'Gramática — Orações subordinadas'
        q['subtema'] = 'Subordinada substantiva completiva'
        q['descricao_breve'] = 'Identificação de oração'
    elif qid == 'III-1':
        q['tema'] = 'Escrita — Texto de opinião'
        q['subtema'] = 'A felicidade e bens materiais'
        q['descricao_breve'] = 'Produção escrita'
        q['palavras_min'] = 200
        q['palavras_max'] = 350
        
    print(f"Updated {qid}")
    
with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("ALL DONE")
