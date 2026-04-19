import json
from pathlib import Path

cc_workspace = Path("workspace/EX-MatA635-EE-2023-CC-VD")
raw_path = cc_workspace / "criterios_raw.json"
output_path = cc_workspace / "criterios_raw_detailed.json"

with open(raw_path, "r") as f:
    cc = json.load(f)

# Comprehensive detailed criteria (ipsis literis)
detailed_data = {
    "2": {
        "solucao": "# 1.º Processo\n\nReconhecer que os comprimentos das semicircunferências são termos consecutivos de uma progressão geométrica: 3 pontos\nIdentificar a razão dessa progressão (2): 2 pontos\nObter o primeiro termo dessa progressão: 2 pontos\nEscrever uma expressão para o comprimento total da composição $\\pi \\frac{1 - 2^{25}}{1 - 2}$ ou equivalente: 5 pontos\nObter o valor pedido $1054 \\text{ km}$: 2 pontos",
        "criterios_parciais": [
            {"pontos": 3, "descricao": "Reconhecer que os comprimentos das semicircunferências são termos consecutivos de uma progressão geométrica"},
            {"pontos": 2, "descricao": "Identificar a razão dessa progressão (2)"},
            {"pontos": 2, "descricao": "Obter o primeiro termo dessa progressão"},
            {"pontos": 5, "descricao": "Escrever uma expressão para o comprimento total da composição $\\pi \\frac{1 - 2^{25}}{1 - 2}$ ou equivalente"},
            {"pontos": 2, "descricao": "Obter o valor pedido $1054 \\text{ km}$"}
        ]
    },
    "4.1": {
        "solucao": "Cálculo de probabilidade de preenchimento de linhas em grelha 3x3.\nApresentar uma expressão correspondente ao número de casos possíveis. 6 pontos\nApresentar uma expressão correspondente ao número de casos favoráveis. 6 pontos\nObter o valor pedido (1/7). 2 pontos",
        "criterios_parciais": [
            {"pontos": 6, "descricao": "Apresentar uma expressão correspondente ao número de casos possíveis"},
            {"pontos": 6, "descricao": "Apresentar uma expressão correspondente ao número de casos favoráveis"},
            {"pontos": 2, "descricao": "Obter o valor pedido (1/7)"}
        ]
    },
    "4.2": {
        "solucao": "Justificação de probabilidade condicionada em contexto.\nInterpreta o significado de $P(C|(A \\cap \\overline{B}))$ 4 pontos\nExplica o valor do denominador (29) 5 pontos\nExplica o valor do numerador (21) 5 pontos",
        "criterios_parciais": [
            {"pontos": 4, "descricao": "Interpretar o significado de $P(C|(A \\cap \\overline{B}))$"},
            {"pontos": 5, "descricao": "Explicar o valor do denominador (29)"},
            {"pontos": 5, "descricao": "Explicar o valor do numerador (21)"}
        ]
    },
    "5.2": {
        "solucao": "Determinação de volume de prisma triangular.\nIdentificar vetor normal OA. 1 ponto\nCoordenadas do ponto médio de OA. 2 pontos\nEquação do plano mediador. 3 pontos\nCoordenadas do ponto B. 3 pontos\nDistância de B ao ponto médio. 2 pontos\nVolume do prisma. 3 pontos",
        "criterios_parciais": [
            {"pontos": 1, "descricao": "Identificar vetor normal OA"},
            {"pontos": 2, "descricao": "Coordenadas do ponto médio de OA"},
            {"pontos": 3, "descricao": "Equação do plano mediador"},
            {"pontos": 3, "descricao": "Coordenadas do ponto B"},
            {"pontos": 2, "descricao": "Distância de B ao ponto médio"},
            {"pontos": 3, "descricao": "Volume do prisma"}
        ]
    },
    "6": {
        "solucao": "Área do triângulo [ABC].\nAltura do triângulo $h = 1 - \\cos \\alpha$. 2 pontos\nBase $AB = \\tan \\alpha$. 2 pontos\nDeterminar $\\tan \\alpha$. 7 pontos\nObter valor pedido. 3 pontos",
        "criterios_parciais": [
            {"pontos": 2, "descricao": "Altura do triângulo $h = 1 - \\cos \\alpha$"},
            {"pontos": 2, "descricao": "Base $AB = \\tan \\alpha$"},
            {"pontos": 7, "descricao": "Determinar $\\tan \\alpha$"},
            {"pontos": 3, "descricao": "Obter valor pedido"}
        ]
    },
    "7.1": {
        "solucao": "Determinar $\\operatorname* { l i m } _ { x \\to 0^{+} } f ( x ) = 2$: 4 pontos\nDeterminar $\\operatorname* { l i m } _ { x \\to 0^{-} } f ( x ) = a$: 8 pontos\nConcluir que $a = 2$: 2 pontos",
        "criterios_parciais": [
            {"pontos": 4, "descricao": "Determinar $\\operatorname* { l i m } _ { x \\to 0^{+} } f ( x )$"},
            {"pontos": 8, "descricao": "Determinar $\\operatorname* { l i m } _ { x \\to 0^{-} } f ( x )$"},
            {"pontos": 2, "descricao": "Concluir que $a = 2$"}
        ]
    },
    "7.2": {
        "solucao": "Escrever $\\operatorname* { l i m } _ { x \\to + \\infty } { \\frac{f ( x )}{x} } = \\operatorname* { l i m } _ { x \\to + \\infty } { \\frac{ \\ln\\bigl( 2 - e^{- x} \\bigr) + x + 2 } { x } }$ 1 ponto\nEscrever ... = \\operatorname* { l i m } _ { x \\to + \\infty } ( \\frac{\\ln ( 2 - e^{- x} ) }{ x } + 1 + \\frac{2}{x} ) 3 pontos\nObter $\\operatorname* { l i m } = 0$ 3 pontos\nObter $\\operatorname* { l i m } = 1$ 2 pontos\nm = 1 1 ponto\nEscrever $\\operatorname* { l i m } ( f(x) - x ) = \ln 2 + 2$ 1 ponto\nObter $b = \\ln 2 + 2$ 2 pontos\nEquação $y = x + \\ln 2 + 2$ 1 ponto",
        "criterios_parciais": [
            {"pontos": 1, "descricao": "Escrever $\\operatorname* { l i m } _ { x \\to + \\infty } { \\frac{f ( x )}{x} } = \\operatorname* { l i m } _ { x \\to + \\infty } { \\frac{ \\ln\\bigl( 2 - e^{- x} \\bigr) + x + 2 } { x } }$"},
            {"pontos": 3, "descricao": "Escrever $\\operatorname* { l i m } _ { x \\to + \\infty } { \\frac{ \\ln \\left( 2 - e^{- x} \\right) + x + 2 } { x } } = \\operatorname* { l i m } _ { x \\to + \\infty } \\left( { \\frac{ \\ln \\left( 2 - e^{- x} \\right) } { x } } + 1 + { \\frac{2}{x} } \\right)$"},
            {"pontos": 3, "descricao": "Obter $\\operatorname* { l i m } _ { x \\to + \\infty } \\left( { \\frac{ \\ln ( 2 - e^{- x} ) } { x } } \\right) = 0$"},
            {"pontos": 2, "descricao": "Obter $\\operatorname* { l i m } _ { x \\to + \\infty } \\left( 1 + \\frac{2}{x} \\right) = 1$"},
            {"pontos": 1, "descricao": "Obter $\\operatorname* { l i m } _ { x \\to + \\infty } \\frac{f(x)}{x} = 1$"},
            {"pontos": 1, "descricao": "Escrever $\\operatorname* { l i m } _ { x \\to + \\infty } ( f(x) - x ) = \\operatorname* { l i m } _ { x \\to + \\infty } ( \\ln ( 2 - e^{- x} ) + 2 )$"},
            {"pontos": 2, "descricao": "Obter $\\operatorname* { l i m } _ { x \\to + \\infty } ( \\ln ( 2 - e^{- x} ) + 2 ) = \\ln 2 + 2$"},
            {"pontos": 1, "descricao": "Obter uma equação da assíntota ($y = x + \\ln 2 + 2$, ou equivalente)"}
        ]
    },
    "9.1": {
        "solucao": "Determinar $g^{\\prime} ( x )$ 2 pontos\nEscrever $g^{\\prime} ( x ) = 0$ 1 ponto\nDeterminar o zero de $g^{\\prime}$ 2 pontos\nApresentar um quadro de sinal de $g^{\\prime}$ e de monotonia de $g$ 3 pontos\nApresentar os intervalos de monotonia de $g$ 2 pontos\nReconhecer que os extremos relativos são $g(0)$ e $g(\\pi/4)$ 2 pontos\nDeterminar $g(0)$ e $g(\\pi/4)$ 2 pontos",
        "criterios_parciais": [
            {"pontos": 2, "descricao": "Determinar $g^{\\prime} ( x )$"},
            {"pontos": 1, "descricao": "Escrever $g^{\\prime} ( x ) = 0$"},
            {"pontos": 2, "descricao": "Determinar o zero de $g^{\\prime}$"},
            {"pontos": 3, "descricao": "Apresentar um quadro de sinal de $g^{\\prime}$ e de monotonia de $g$"},
            {"pontos": 2, "descricao": "Apresentar os intervalos de monotonia de $g$"},
            {"pontos": 2, "descricao": "Reconhecer que os extremos relativos de $g$ são $g ( 0 )$ e $g \\left( \\frac{\\pi}{4} \\right)$"},
            {"pontos": 2, "descricao": "Determinar $g ( 0 )$ e $g \\left( \\frac{\\pi}{4} \\right)$ ($1$ e $\\frac{\\sqrt{2}}{2} e^{\\frac{\\pi}{4}}$)"}
        ]
    },
    "9.2": {
        "solucao": "Equacionar o problema $g ( x ) = x$ 3 pontos\nConsiderar a função $f(x) = g(x) - x$ 3 pontos\nReferir que f é contínua em $[\\pi/3, \\pi/2]$ 2 pontos\nDeterminar $f(\\pi/3)$ 1 ponto\nDeterminar $f(\\pi/2)$ 1 ponto\nConcluir $f(\\pi/2) < 0 < f(\\pi/3)$ 2 pontos\nConcluir o pretendido 2 pontos",
        "criterios_parciais": [
            {"pontos": 3, "descricao": "Equacionar o problema ($g ( x ) = x$, ou equivalente)"},
            {"pontos": 3, "descricao": "Considerar a função $f$, definida por $f ( x ) = g ( x ) - x$"},
            {"pontos": 2, "descricao": "Referir que a função $f$ é contínua em $\\left[ \\frac{\\pi}{3} , \\frac{\\pi}{2} \\right]$"},
            {"pontos": 1, "descricao": "Determinar $f \\left( \\frac{\\pi}{3} \\right)$"},
            {"pontos": 1, "descricao": "Determinar $f \\left( \\frac{\\pi}{2} \\right)$"},
            {"pontos": 2, "descricao": "Concluir que $f \\left( \\frac{\\pi}{2} \\right) < 0 < f \\left( \\frac{\\pi}{3} \\right)$ (ou equivalente)"},
            {"pontos": 2, "descricao": "Concluir o pretendido"}
        ]
    },
    "10": {
        "solucao": "Obter $3 e^{x} - 3 e^{- x} = e^{x} + e^{- x}$ 3 pontos\nObter $2 e^{x} - 4 e^{- x} = 0$ 3 pontos\nObter $e^{2 x} = 2$ 4 pontos\nObter a solução $x = (\\ln 2)/2$ 4 pontos",
        "criterios_parciais": [
            {"pontos": 3, "descricao": "Obter $3 e^{x} - 3 e^{- x} = e^{x} + e^{- x}$"},
            {"pontos": 3, "descricao": "Obter $2 e^{x} - 4 e^{- x} = 0$"},
            {"pontos": 4, "descricao": "Obter $e^{2 x} = 2$"},
            {"pontos": 4, "descricao": "Obter a solução da equação $\\left( \\frac{\\ln 2}{2} \\right)$"}
        ]
    },
    "11": {
        "solucao": "Diâmetro da circunferência (6): 2 pontos\nEquação $d(t) = 6$: 4 pontos\nGráficos na calculadora: 4 pontos\nAssinalar pontos relevantes: 2 pontos\nValores pedidos (1,4 s e 3,3 s): 2 pontos",
        "criterios_parciais": [
            {"pontos": 2, "descricao": "Determinar o diâmetro da circunferência (6)"},
            {"pontos": 4, "descricao": "Apresentar a equação $d ( t ) = 6$ (ou equivalente)"},
            {"pontos": 4, "descricao": "Representar o(s) gráfico(s) da(s) função(ões) visualizado(s) na calculadora"},
            {"pontos": 2, "descricao": "Assinalar os pontos relevantes"},
            {"pontos": 2, "descricao": "Apresentar os valores pedidos (1,4 s e 3,3 s)"}
        ]
    },
    "13": {
        "solucao": "# 1.º Processo\n\nSubstituir $i^{23}$ por $-i$: 1 ponto\nObter $z_1 - i = -6i$: 1 ponto\nObter $-6i = 6 e^{i 3\\pi/2}$: 1 ponto\nObter $z_2 = 2 e^{i 4\\pi/3}$: 2 pontos\nArgumento de $z_2^n$: $4n\\pi/3$: 1 ponto\nArgumento de $w$: $3\\pi/2 - 4n\\pi/3$: 2 pontos\nCondição de imaginário puro: 2 pontos\n$n = (3 - 3k)/4$: 2 pontos\nValor pedido (3): 2 pontos",
        "criterios_parciais": [
            {"pontos": 1, "descricao": "Substituir $i^{23}$ por $- i$"},
            {"pontos": 1, "descricao": "Obter $z_{1} - i = - 6 i$"},
            {"pontos": 1, "descricao": "Obter $- 6 i = 6 e ^ { i \\frac{3 \\pi}{2} }$ (ou equivalente)"},
            {"pontos": 2, "descricao": "Obter $z_{2} = 2 e ^ { i \\frac{4 \\pi}{3} }$ (ou equivalente)"},
            {"pontos": 1, "descricao": "Obter um argumento de $z_{2}^n$ em função de $n$ (por exemplo, $\\frac{4 n \\pi}{3}$)"},
            {"pontos": 2, "descricao": "Obter um argumento de $w$ em função de $n$ (por exemplo, $\\frac{3 \\pi}{2} - \\frac{4 n \\pi}{3}$)"},
            {"pontos": 2, "descricao": "Reconhecer que $w$ é um imaginário puro se $\\frac{3 \\pi}{2} - \\frac{4 n \\pi}{3} = \\frac{\\pi}{2} + k \\pi, k \\in \\mathbb{ Z }$"},
            {"pontos": 2, "descricao": "Obter $n = \\frac{3 - 3 k}{4}, k \\in \\mathbb{ Z }$"},
            {"pontos": 2, "descricao": "Obter o valor pedido (3)"}
        ]
    },
    "14": {
        "solucao": "Coordenadas A e B ($x_1, x_1^2$ e $x_2, x_2^2$): 2 pontos\n$f^{\\prime}(x)$: 2 pontos\nEquação da tangente em A: 2 pontos\nEquação da tangente em B: 2 pontos\nAbcissa do ponto de intersecção: 3 pontos\nReconhecer ponto médio: 1 ponto\nConcluir pretendido: 2 pontos",
        "criterios_parciais": [
            {"pontos": 2, "descricao": "Designar por $x_1$ e $x_2$ as abcissas de A e B e reconhecer as ordenadas $x_1^2$ e $x_2^2$"},
            {"pontos": 2, "descricao": "Determinar $f^{\\prime} ( x )$"},
            {"pontos": 2, "descricao": "Obter uma equação da reta tangente ao gráfico da função $f$ no ponto $A$"},
            {"pontos": 2, "descricao": "Obter uma equação da reta tangente ao gráfico da função $f$ no ponto $B$"},
            {"pontos": 3, "descricao": "Obter a abcissa do ponto de intersecção das retas tangentes"},
            {"pontos": 1, "descricao": "Reconhecer que a abcissa obtida é o ponto médio"},
            {"pontos": 2, "descricao": "Concluir o pretendido"}
        ]
    }
}

new_cc = []
for item in cc:
    id_item = item["id_item"]
    if id_item in detailed_data:
        item["criterios_parciais"] = detailed_data[id_item]["criterios_parciais"]
        item["solucao"] = detailed_data[id_item]["solucao"]
    item["reviewed"] = True
    new_cc.append(item)

with open(output_path, "w") as f:
    json.dump(new_cc, f, indent=2, ensure_ascii=False)

print(f"Created {output_path}")
