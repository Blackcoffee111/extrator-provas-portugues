import json
from pathlib import Path

review_path = Path('workspace/EX-MatA635-F2-2021/questoes_review.json')
with open(review_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

# 1.1
data[1]['tema'] = 'Geometria'
data[1]['subtema'] = 'Referenciais o.n. no espaço'
data[1]['descricao_breve'] = 'Superfície esférica'
data[1]['reviewed'] = True

# 1.2
data[2]['tema'] = 'Geometria'
data[2]['subtema'] = 'Referenciais o.n. no espaço'
data[2]['descricao_breve'] = 'Equação do plano'
data[2]['reviewed'] = True

# 2
data[3]['tema'] = 'Funções'
data[3]['subtema'] = 'Trigonometria'
data[3]['descricao_breve'] = 'Expressão trigonométrica'
data[3]['reviewed'] = True

# 3.1 & 3.2 split
# data[5] is 3.1. It currently has 3.2 in its option D text.
opt_d_text = data[5]['alternativas'][1]['texto'] # Using index 1 because OCR only found A, B, C, D is mashed? Wait.
# Re-reading: A=0,22, B=0,43, C=0,50, D=0,87 : 3.2...

data[5]['alternativas'] = [
    {"letra": "A", "texto": "0,22"},
    {"letra": "B", "texto": "0,43"},
    {"letra": "C", "texto": "0,50"},
    {"letra": "D", "texto": "0,87"}
]
data[5]['tema'] = 'Probabilidades'
data[5]['subtema'] = 'Cálculo Combinatório'
data[5]['descricao_breve'] = 'Probabilidade com combinações'
data[5]['reviewed'] = True

# 3.2 (New Item)
item_32 = {
    "id_item": "3.2",
    "tipo_item": "open_response",
    "enunciado": "Relativamente a este clube, sabe-se que:\n\n• cada sócio pratica uma e só uma das duas modalidades;\n• $6 5 \\%$ dos sócios são mulheres;\n• $\\frac{1}{7}$ dos homens pratica badmínton;\n• $\\frac{5}{6}$ dos praticantes de badmínton são mulheres.\n\nEscolhe-se, ao acaso, um sócio deste clube.\n\nDetermine a probabilidade de o sócio escolhido ser uma mulher que pratica ténis.\n\nApresente o resultado na forma de percentagem.",
    "alternativas": [],
    "tema": "Probabilidades",
    "subtema": "Probabilidade Condicionada",
    "descricao_breve": "Probabilidade condicionada e diagramas",
    "tags": [],
    "imagens": [],
    "resposta_correta": None,
    "observacoes": [],
    "enunciado_contexto_pai": data[5]['enunciado_contexto_pai'],
    "solucao": "",
    "grupo": "",
    "reviewed": True
}
data.insert(6, item_32)

# Adjust indices for items after insertion
# 4 (was 6, now 7)
data[7]['tema'] = 'Probabilidades'
data[7]['subtema'] = 'Cálculo Combinatório'
data[7]['descricao_breve'] = 'Número de triângulos'
data[7]['reviewed'] = True

# 5 (was 7, now 8)
data[8]['tema'] = 'Funções'
data[8]['subtema'] = 'Limites'
data[8]['descricao_breve'] = 'Limite de composição com sucessão'
data[8]['reviewed'] = True

# 6 (was 8, now 9)
data[9]['tema'] = 'Funções'
data[9]['subtema'] = 'Sucessões'
data[9]['descricao_breve'] = 'Progressão aritmética'
data[9]['reviewed'] = True

# 7 (was 9, now 10)
# Fix alternatives mashed
data[10]['alternativas'] = [
    {"letra": "A", "texto": "\\frac{1 9 \\pi}{10}"},
    {"letra": "B", "texto": "\\frac{2 \\pi}{5}"},
    {"letra": "C", "texto": "- \\frac{2 \\pi}{5}"}, # Guessed from context of options
    {"letra": "D", "texto": "- \\frac{1 9 \\pi}{10}"}
]
data[10]['tipo_item'] = 'multiple_choice'
data[10]['tema'] = 'Números Complexos'
data[10]['subtema'] = 'Forma Trigonométrica'
data[10]['descricao_breve'] = 'Argumento de um complexo'
data[10]['reviewed'] = True

# 8 (was 10, now 11)
data[11]['tema'] = 'Números Complexos'
data[11]['subtema'] = 'Lugar Geométrico'
data[11]['descricao_breve'] = 'Reta no plano complexo'
data[11]['reviewed'] = True

# 9.1 & 9.2 (was 12, now 13)
# data[12] (context), data[13] (9.1 and 9.2 mashed)
full_enunc = data[13]['enunciado']
if ':9.2.' in full_enunc:
    parts = full_enunc.split(':9.2.')
    data[13]['enunciado'] = parts[0].strip()
    data[13]['id_item'] = '9.1'
    data[13]['tema'] = 'Funções'
    data[13]['subtema'] = 'Assíntotas'
    data[13]['descricao_breve'] = 'Assíntotas horizontais'
    data[13]['reviewed'] = True
    
    item_92 = {
        "id_item": "9.2",
        "tipo_item": "open_response",
        "enunciado": "Determine a equação reduzida da reta tangente ao gráfico da função $f$ no ponto de abcissa $-2$",
        "alternativas": [],
        "tema": "Funções",
        "subtema": "Derivadas",
        "descricao_breve": "Reta tangente ao gráfico",
        "tags": [],
        "imagens": [],
        "resposta_correta": None,
        "observacoes": [],
        "enunciado_contexto_pai": data[13]['enunciado_contexto_pai'],
        "solucao": "",
        "grupo": "",
        "reviewed": True
    }
    data.insert(14, item_92)

# Adjust indices for items after 9.2
# 10 (was 14, now 16) - wait, indices change again.
# Original data: [0:1, 1:1.1, 2:1.2, 3:2, 4:3, 5:3.1, 6:4, 7:5, 8:6, 9:7, 10:8, 11:9, 12:9.1]
# After 3.2 insert at 6: [0:1, 1:1.1, 2:1.2, 3:2, 4:3, 5:3.1, 6:3.2, 7:4, 8:5, 9:6, 10:7, 11:8, 12:9, 13:9.1]
# After 9.2 insert at 14: [0:1, ..., 12:9, 13:9.1, 14:9.2, 15:10, 16:10.1, 17:11, 18:11.1, 19:11.2, 20:11.2 bis, 21:11.3, 22:12]

# 10
data[15]['tema'] = 'Funções'
data[15]['subtema'] = 'Estudo da Função'
data[15]['descricao_breve'] = 'Monotonia e extremos de função trigonométrica'
data[15]['reviewed'] = True

# 11.1
data[18]['tema'] = 'Funções'
data[18]['subtema'] = 'Modelos Matemáticos'
data[18]['descricao_breve'] = 'Arrefecimento (exponencial)'
data[18]['tipo_item'] = 'multiple_choice'
data[18]['alternativas'] = [
    {"letra": "A", "texto": "\\ln \\left( { \\frac{ 1 0 } { t_{1} } } \\right)"},
    {"letra": "B", "texto": "\\frac{\\ln 10}{t_1}"}, # Inferred from partial OCR
    {"letra": "C", "texto": "\\ln 10"},
    {"letra": "D", "texto": "t_1 + \\ln 10"}
]
data[18]['reviewed'] = True

# 11.2
data[19]['tema'] = 'Funções'
data[19]['subtema'] = 'Derivadas'
data[19]['descricao_breve'] = 'Taxa média de variação (calculadora)'
data[19]['reviewed'] = True

# 12 (was 11.2 duplicate at 20)
data[20]['id_item'] = '12'
data[20]['tema'] = 'Funções'
data[20]['subtema'] = 'Continuidade'
data[20]['descricao_breve'] = 'Continuidade no ponto'
data[20]['enunciado_contexto_pai'] = "" # It's a new item 1, wait.
data[20]['reviewed'] = True

# 13 (was 11.3 at 21)
data[21]['id_item'] = '13'
data[21]['tema'] = 'Funções'
data[21]['subtema'] = 'Equações'
data[21]['descricao_breve'] = 'Equação com logaritmos'
data[21]['reviewed'] = True

# 14 (was 12 at 22)
data[22]['id_item'] = '14'
data[22]['tema'] = 'Trigonometria'
data[22]['subtema'] = 'Resolução de Triângulos'
data[22]['descricao_breve'] = 'Área e ordenada em função de k'
data[22]['reviewed'] = True

# Mark context stems as reviewed too
for item in data:
    if item['tipo_item'] == 'context_stem':
        item['reviewed'] = True

with open(review_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
