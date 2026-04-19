import json

criterios = [
    {
        "id_item": "1",
        "cotacao_total": 12,
        "tipo": "multiple_choice",
        "resposta_correta": "D",
        "solucao": "",
        "criterios_parciais": [],
        "resolucoes_alternativas": [],
        "status": "draft",
        "texto_original": "Opção (D)",
        "fonte": "",
        "observacoes": [],
        "imagens": [],
        "contexto": "",
        "reviewed": True
    },
    {
        "id_item": "2",
        "cotacao_total": 14,
        "tipo": "open_response",
        "resposta_correta": None,
        "solucao": "Este item pode ser resolvido por, pelo menos, dois processos.\n\n# 1.º Processo\n\nReconhecer que os comprimentos das semicircunferências são termos consecutivos de uma progressão geométrica: 3 pontos\nIdentificar a razão dessa progressão (2): 2 pontos\nObter o primeiro termo dessa progressão: 2 pontos\nEscrever uma expressão para o comprimento total da composição $\\pi \\frac{1 - 2^{25}}{1 - 2}$, ou equivalente: 5 pontos\nObter o valor pedido ($1054 \\text{ km}$): 2 pontos\n\n# 2.º Processo\n\nReconhecer que os raios das semicircunferências são termos consecutivos de uma progressão geométrica: 2 pontos\nIdentificar a razão dessa progressão (2): 2 pontos\nIdentificar o primeiro termo da progressão: 1 ponto\nEscrever uma expressão para a soma dos comprimentos dos raios $\\frac{1 - 2^{25}}{1 - 2}$, ou equivalente: 4 pontos\nEscrever uma expressão para o comprimento total da composição: 3 pontos\nObter o valor pedido ($1054 \\text{ km}$): 2 pontos",
        "criterios_parciais": [
            {"pontos": 3, "descricao": "Reconhecer que os comprimentos das semicircunferências são termos consecutivos de uma progressão geométrica"},
            {"pontos": 2, "descricao": "Identificar a razão dessa progressão (2)"},
            {"pontos": 2, "descricao": "Obter o primeiro termo dessa progressão"},
            {"pontos": 5, "descricao": "Escrever uma expressão para o comprimento total da composição $\\pi \\frac{1 - 2^{25}}{1 - 2}$, ou equivalente"},
            {"pontos": 2, "descricao": "Obter o valor pedido ($1054 \\text{ km}$)"}
        ],
        "resolucoes_alternativas": [],
        "status": "draft",
        "texto_original": "Este item pode ser resolvido por, pelo menos, dois processos.",
        "fonte": "",
        "observacoes": [],
        "reviewed": True
    },
    {
        "id_item": "3",
        "cotacao_total": 12,
        "tipo": "multiple_choice",
        "resposta_correta": "B",
        "solucao": "",
        "criterios_parciais": [],
        "resolucoes_alternativas": [],
        "status": "draft",
        "texto_original": "Opção (B)",
        "reviewed": True
    },
    {
        "id_item": "4.1",
        "cotacao_total": 14,
        "tipo": "open_response",
        "resposta_correta": None,
        "solucao": "Este item pode ser resolvido por, pelo menos, quatro processos.\n\n# 1.º Processo\nApresentar uma expressão correspondente ao número de casos possíveis ($^{9}C_{4} \\times ^{5}C_{2}$) (ver nota 1): 6 pontos\nApresentar uma expressão correspondente ao número de casos favoráveis ($3 \\times 6 \\times ^{5}C_{2}$) (ver nota 2): 6 pontos\nObter o valor pedido (1/7) (ver nota 3): 2 pontos\n\n# 2.º Processo\nApresentar uma expressão correspondente ao número de casos possíveis (9!) (ver nota 1): 6 pontos\nApresentar uma expressão correspondente ao número de casos favoráveis ($3 \\times ^{4}A_{3} \\times 6!$) (ver nota 2): 6 pontos\nObter o valor pedido (1/7) (ver nota 3): 2 pontos\n\n# 3.º Processo\nConsidere-se apenas a disposição dos bombons com recheio de amêndoa.\nApresentar uma expressão correspondente ao número de casos possíveis ($^{9}C_{4}$) (ver nota 1): 6 pontos\nApresentar uma expressão correspondente ao número de casos favoráveis ($3 \\times 6$) (ver nota 2): 6 pontos\nObter o valor pedido (1/7) (ver nota 3): 2 pontos\n\n# 4.º Processo\nConsidere-se apenas a disposição dos bombons com recheio de amêndoa.\nApresentar uma expressão correspondente ao número de casos possíveis ($^{9}A_{4}$) (ver nota 1): 6 pontos\nApresentar uma expressão correspondente ao número de casos favoráveis ($^{4}A_{3} \\times 3 \\times 6$) (ver nota 2): 6 pontos\nObter o valor pedido (1/7) (ver nota 3): 2 pontos\n\n# Notas:\n1. Se a expressão apresentada não for equivalente à indicada, a pontuação a atribuir nesta etapa é 0 pontos.\n2. Se a expressão apresentada não for equivalente à indicada, a pontuação a atribuir nesta etapa é 0 pontos.\n3. Se o valor obtido não pertencer ao intervalo [0, 1], a pontuação a atribuir nesta etapa é 0 pontos.",
        "criterios_parciais": [
            {"pontos": 6, "descricao": "Apresentar uma expressão correspondente ao número de casos possíveis ($^{9}C_{4} \\times ^{5}C_{2}$)"},
            {"pontos": 6, "descricao": "Apresentar uma expressão correspondente ao número de casos favoráveis ($3 \\times 6 \\times ^{5}C_{2}$)"},
            {"pontos": 2, "descricao": "Obter o valor pedido (1/7)"}
        ],
        "resolucoes_alternativas": [],
        "status": "draft",
        "reviewed": True
    },
    {
        "id_item": "4.2",
        "cotacao_total": 14,
        "tipo": "open_response",
        "resposta_correta": None,
        "solucao": "# Tópicos de resposta\n\n- Interpreta o significado de $P(C | (A \\cap \\overline{B}))$ tendo em conta o contexto descrito: A expressão $P(C | (A \\cap \\overline{B}))$ representa a probabilidade de o terceiro bombom, selecionado ao acaso, ter recheio de caramelo, se o primeiro bombom selecionado tiver recheio de frutos secos e o segundo tiver recheio de caramelo.\n- Explica o valor do denominador (29): Como inicialmente existem 31 bombons, após a seleção dos dois primeiros, existem 29 bombons disponíveis para a seleção do terceiro bombom.\n- Explica o valor do numerador (21): Como inicialmente existem 22 bombons de caramelo, após a seleção de um bombom de frutos secos e de um bombom de caramelo, existem 21 bombons de caramelo disponíveis para a seleção do terceiro bombom.",
        "criterios_parciais": [
            {"pontos": 4, "descricao": "Interpreta o significado de $P(C | (A \\cap \\overline{B}))$ tendo em conta o contexto descrito"},
            {"pontos": 5, "descricao": "Explica o valor do denominador (29)"},
            {"pontos": 5, "descricao": "Explica o valor do numerador (21)"}
        ],
        "status": "draft",
        "imagens": ["imagens_extraidas/16a20d099a88980f59b49e052ddae947bd108283c2d5ead1a88697cc6f7e1325.jpg"],
        "reviewed": True
    },
    {
        "id_item": "5.1",
        "cotacao_total": 12,
        "tipo": "multiple_choice",
        "resposta_correta": "C",
        "solucao": "",
        "status": "draft",
        "texto_original": "Opção (C)",
        "reviewed": True
    },
    {
        "id_item": "5.2",
        "cotacao_total": 14,
        "tipo": "open_response",
        "resposta_correta": None,
        "solucao": "Este item pode ser resolvido por, pelo menos, dois processos.\n\n# 1.º Processo\n\nIdentificar $\\overrightarrow{OA}$ como vetor normal ao plano mediador do segmento de reta $[OA]$: 1 ponto\nIdentificar as coordenadas do vetor $\\overrightarrow{OA}$ (($2\\sqrt{3}, 6, 0$)): 1 ponto\nObter as coordenadas do ponto médio do segmento de reta $[OA]$ (($\\sqrt{3}, 3, 0$)): 1 ponto\nObter uma equação do plano mediador do segmento de reta $[OA]$: 3 pontos\n- Escrever $2\\sqrt{3}x + 6y + d = 0$ (ou equivalente): 1 ponto\n- Escrever $2\\sqrt{3} \\times \\sqrt{3} + 6 \\times 3 + d = 0$: 1 ponto\n- Obter o valor de $d$ (-24): 1 ponto\nReconhecer que as coordenadas do ponto $B$ são da forma $(\\sqrt{3}k, 16 - 5k, 0)$: 1 ponto\nEscrever $2\\sqrt{3} \\times \\sqrt{3}k + 6(16 - 5k) - 24 = 0$ (ou equivalente): 1 ponto\nObter o valor de $k$ (3): 1 ponto\nObter as coordenadas do ponto $B$ (($3\\sqrt{3}, 1, 0$)): 1 ponto\nObter a distância do ponto $B$ ao ponto médio do segmento de reta $[OA]$ (4): 1 ponto\nObter $\\overline{OA}$ ($4\\sqrt{3}$): 1 ponto\nObter o valor pedido ($40\\sqrt{3}$, ou equivalente): 2 pontos\n\n# 2.º Processo\n\nDesignemos por $(a, b, 0)$ as coordenadas do ponto $B$.\nEscrever $a^2 + b^2 = (a - 2\\sqrt{3})^2 + (b - 6)^2$ (ou equivalente): 3 pontos\nObter a equação $4\\sqrt{3}a + 12b - 48 = 0$ (ou equivalente): 2 pontos\nReconhecer que as coordenadas do ponto $B$ são da forma $(\\sqrt{3}k, 16 - 5k, 0)$: 1 ponto\nEscrever $4\\sqrt{3} \\times \\sqrt{3}k + 12(16 - 5k) - 48 = 0$ (ou equivalente): 1 ponto\nObter o valor de $k$ (3): 1 ponto\nObter as coordenadas do ponto $B$ (($3\\sqrt{3}, 1, 0$)): 1 ponto\nObter as coordenadas do ponto médio do segmento de reta $[OA]$ (($\\sqrt{3}, 3, 0$)): 1 ponto\nObter a distância do ponto $B$ ao ponto médio do segmento de reta $[OA]$ (4): 1 ponto\nObter $\\overline{OA}$ ($4\\sqrt{3}$): 1 ponto\nObter o valor pedido ($40\\sqrt{3}$, ou equivalente): 2 pontos",
        "criterios_parciais": [
            {"pontos": 1, "descricao": "Identificar $\\overrightarrow{OA}$ como vetor normal ao plano mediador do segmento de reta $[OA]$"},
            {"pontos": 1, "descricao": "Identificar as coordenadas do vetor $\\overrightarrow{OA}$ ($2\\sqrt{3}, 6, 0$)"},
            {"pontos": 1, "descricao": "Obter as coordenadas do ponto médio do segmento de reta $[OA]$ ($\\sqrt{3}, 3, 0$)"},
            {"pontos": 1, "descricao": "Escrever $2\\sqrt{3}x + 6y + d = 0$ (ou equivalente)"},
            {"pontos": 1, "descricao": "Escrever $2\\sqrt{3} \\times \\sqrt{3} + 6 \\times 3 + d = 0$"},
            {"pontos": 1, "descricao": "Obter o valor de $d$ (-24)"},
            {"pontos": 1, "descricao": "Reconhecer que as coordenadas do ponto $B$ são da forma $(\\sqrt{3}k, 16 - 5k, 0)$"},
            {"pontos": 1, "descricao": "Escrever $2\\sqrt{3} \\times \\sqrt{3}k + 6(16 - 5k) - 24 = 0$ (ou equivalente)"},
            {"pontos": 1, "descricao": "Obter o valor de $k$ (3)"},
            {"pontos": 1, "descricao": "Obter as coordenadas do ponto $B$ ($3\\sqrt{3}, 1, 0$)"},
            {"pontos": 1, "descricao": "Obter a distância do ponto $B$ ao ponto médio do segmento de reta $[OA]$ (4)"},
            {"pontos": 1, "descricao": "Obter $\\overline{OA}$ ($4\\sqrt{3}$)"},
            {"pontos": 2, "descricao": "Obter o valor pedido ($40\\sqrt{3}$)"}
        ],
        "status": "draft",
        "reviewed": True
    },
    {
        "id_item": "6",
        "cotacao_total": 14,
        "tipo": "open_response",
        "resposta_correta": None,
        "solucao": "Reconhecer que a altura do triângulo $[ABC]$ relativa à base $[AB]$ é $1 - \\cos \\alpha$: 2 pontos\nReconhecer que $\\overline{AB} = \\tan \\alpha$: 2 pontos\nDeterminar $\\tan \\alpha$: 7 pontos\n\nEsta etapa pode ser resolvido por, pelos menos, dois processos.\n\n# 1.º Processo\nEscrever $\\tan^2 \\alpha + 1 = \\frac{1}{\\cos^2 \\alpha}$ (ou equivalente): 3 pontos\nObter $\\tan \\alpha = \\sqrt{8}$: 4 pontos\n\n# 2.º Processo\nEscrever $\\sin^2 \\alpha + \\cos^2 \\alpha = 1$ (ou equivalente): 2 pontos\nObter $\\sin \\alpha = \\frac{\\sqrt{8}}{3}$: 2 pontos\nEscrever $\\tan \\alpha = \\frac{\\sin \\alpha}{\\cos \\alpha}$ (ou equivalente): 1 ponto\nObter $\\tan \\alpha = \\sqrt{8}$: 2 pontos\n\nObter o valor pedido ($\\frac{2\\sqrt{2}}{3}$, ou equivalente): 3 pontos",
        "criterios_parciais": [
            {"pontos": 2, "descricao": "Reconhecer que a altura do triângulo $[ABC]$ relativa à base $[AB]$ é $1 - \\cos \\alpha$"},
            {"pontos": 2, "descricao": "Reconhecer que $\\overline{AB} = \\tan \\alpha$"},
            {"pontos": 3, "descricao": "Escrever $\\tan^2 \\alpha + 1 = \\frac{1}{\\cos^2 \\alpha}$ (ou equivalente)"},
            {"pontos": 4, "descricao": "Obter $\\tan \\alpha = \\sqrt{8}$"},
            {"pontos": 3, "descricao": "Obter o valor pedido ($\\frac{2\\sqrt{2}}{3}$, ou equivalente)"}
        ],
        "status": "draft",
        "reviewed": True
    },
    {
        "id_item": "7.1",
        "cotacao_total": 14,
        "tipo": "open_response",
        "resposta_correta": None,
        "solucao": "Determinar $\\lim_{x \\to 0^+} f(x)$: 2 pontos\n- Reconhecer que $\\lim_{x \\to 0^+} f(x) = \\lim_{x \\to 0^+} (\\ln(2 - e^{-x}) + x + 2)$: 1 ponto\n- Obter $\\lim_{x \\to 0^+} f(x) = 2$: 1 ponto\n\nDeterminar $\\lim_{x \\to 0^-} f(x)$: 10 pontos\n- Reconhecer que $\\lim_{x \\to 0^-} f(x) = \\lim_{x \\to 0^-} \\frac{\\sin(ax)}{e^x - 1}$: 1 ponto\n- Escrever $\\lim_{x \\to 0^-} \\frac{\\sin(ax)}{e^x - 1} = \\lim_{x \\to 0^-} \\frac{\\sin(ax)}{x} \\times \\lim_{x \\to 0^-} \\frac{x}{e^x - 1}$: 3 pontos\n- Escrever $\\lim_{x \\to 0^-} \\frac{\\sin(ax)}{x} \\stackrel{y=ax}{=} a \\times \\lim_{y \\to 0^-} \\frac{\\sin y}{y}$: 2 pontos\n- Obter $a \\times \\lim_{y \\to 0^-} \\frac{\\sin y}{y} = a$: 1 ponto\n- Obter $\\lim_{x \\to 0^-} \\frac{x}{e^x - 1} = \\lim_{x \\to 0^-} (\\frac{e^x - 1}{x})^{-1}$: 1 ponto\n- Reconhecer que $\\lim_{x \\to 0^-} (\\frac{e^x - 1}{x})^{-1} = (\\lim_{x \\to 0^-} \\frac{e^x - 1}{x})^{-1}$: 1 ponto\n- Concluir que $\\lim_{x \\to 0^-} f(x) = a \\times 1 = a$: 1 ponto\n\nConcluir que $a = 2$: 2 pontos",
        "criterios_parciais": [
            {"pontos": 1, "descricao": "Reconhecer que $\\lim_{x \\to 0^+} f(x) = \\lim_{x \\to 0^+} (\\ln(2 - e^{-x}) + x + 2)$"},
            {"pontos": 1, "descricao": "Obter $\\lim_{x \\to 0^+} f(x) = 2$"},
            {"pontos": 1, "descricao": "Reconhecer que $\\lim_{x \\to 0^-} f(x) = \\lim_{x \\to 0^-} \\frac{\\sin(ax)}{e^x - 1}$"},
            {"pontos": 3, "descricao": "Escrever $\\lim_{x \\to 0^-} \\frac{\\sin(ax)}{e^x - 1} = \\lim_{x \\to 0^-} \\frac{\\sin(ax)}{x} \\times \\lim_{x \\to 0^-} \\frac{x}{e^x - 1}$"},
            {"pontos": 2, "descricao": "Escrever $\\lim_{x \\to 0^-} \\frac{\\sin(ax)}{x} = a \\times \\lim_{y \\to 0^-} \\frac{\\sin y}{y}$"},
            {"pontos": 1, "descricao": "Obter $a \\times \\lim_{y \\to 0^-} \\frac{\\sin y}{y} = a$"},
            {"pontos": 1, "descricao": "Obter $\\lim_{x \\to 0^-} \\frac{x}{e^x - 1} = \\lim_{x \\to 0^-} (\\frac{e^x - 1}{x})^{-1}$"},
            {"pontos": 1, "descricao": "Reconhecer que $\\lim_{x \\to 0^-} (\\frac{e^x - 1}{x})^{-1} = (\\lim_{x \\to 0^-} \\frac{e^x - 1}{x})^{-1}$"},
            {"pontos": 1, "descricao": "Concluir que $\\lim_{x \\to 0^-} f(x) = a$"},
            {"pontos": 2, "descricao": "Concluir que $a = 2$"}
        ],
        "status": "draft",
        "reviewed": True
    },
    {
        "id_item": "7.2",
        "cotacao_total": 14,
        "tipo": "open_response",
        "resposta_correta": None,
        "solucao": "Escrever $\\lim_{x \\to +\\infty} \\frac{f(x)}{x} = \\lim_{x \\to +\\infty} \\frac{\\ln(2 - e^{-x}) + x + 2}{x}$: 1 ponto\nEscrever $\\lim_{x \\to +\\infty} \\frac{\\ln(2 - e^{-x}) + x + 2}{x} = \\lim_{x \\to +\\infty} (\\frac{\\ln(2 - e^{-x})}{x} + 1 + \\frac{2}{x})$: 3 pontos\nObter $\\lim_{x \\to +\\infty} \\frac{\\ln(2 - e^{-x})}{x} = 0$: 3 pontos\nObter $\\lim_{x \\to +\\infty} (1 + \\frac{2}{x}) = 1$: 2 pontos\nObter $\\lim_{x \\to +\\infty} \\frac{f(x)}{x} = 1$: 1 ponto\nEscrever $\\lim_{x \\to +\\infty} (f(x) - x) = \\lim_{x \\to +\\infty} (\\ln(2 - e^{-x}) + 2)$: 1 ponto\nObter $\\lim_{x \\to +\\infty} (\\ln(2 - e^{-x}) + 2) = \\ln 2 + 2$: 2 pontos\nObter uma equação da assíntota ($y = x + \\ln 2 + 2$, ou equivalente): 1 ponto",
        "criterios_parciais": [
            {"pontos": 1, "descricao": "Escrever $\\lim_{x \\to +\\infty} \\frac{f(x)}{x} = \\lim_{x \\to +\\infty} \\frac{\\ln(2 - e^{-x}) + x + 2}{x}$"},
            {"pontos": 3, "descricao": "Escrever $\\lim_{x \\to +\\infty} \\frac{\\ln(2 - e^{-x}) + x + 2}{x} = \\lim_{x \\to +\\infty} (\\frac{\\ln(2 - e^{-x})}{x} + 1 + \\frac{2}{x})$"},
            {"pontos": 3, "descricao": "Obter $\\lim_{x \\to +\\infty} \\frac{\\ln(2 - e^{-x})}{x} = 0$"},
            {"pontos": 2, "descricao": "Obter $\\lim_{x \\to +\\infty} (1 + \\frac{2}{x}) = 1$"},
            {"pontos": 1, "descricao": "Obter $\\lim_{x \\to +\\infty} \\frac{f(x)}{x} = 1$"},
            {"pontos": 1, "descricao": "Escrever $\\lim_{x \\to +\\infty} (f(x) - x) = \\lim_{x \\to +\\infty} (\\ln(2 - e^{-x}) + 2)$"},
            {"pontos": 2, "descricao": "Obter $\\lim_{x \\to +\\infty} (\\ln(2 - e^{-x}) + 2) = \\ln 2 + 2$"},
            {"pontos": 1, "descricao": "Obter uma equação da assíntota ($y = x + \\ln 2 + 2$)"}
        ],
        "status": "draft",
        "reviewed": True
    },
    {
        "id_item": "8",
        "cotacao_total": 12,
        "tipo": "multiple_choice",
        "resposta_correta": "B",
        "solucao": "",
        "status": "draft",
        "texto_original": "Opção (B)",
        "reviewed": True
    },
    {
        "id_item": "9.1",
        "cotacao_total": 14,
        "tipo": "open_response",
        "resposta_correta": None,
        "solucao": "Determinar $g'(x)$ (ver nota 1): 2 pontos\nEscrever $g'(x) = 0$: 1 ponto\nDeterminar o zero de $g'$: 2 pontos\nApresentar um quadro de sinal de $g'$ e de monotonia de $g$: 3 pontos\nApresentar os intervalos de monotonia de $g$ (ver nota 2): 2 pontos\nReconhecer que os extremos são $g(0)$ e $g(\\frac{\\pi}{4})$: 2 pontos\nDeterminar $g(0)$ e $g(\\frac{\\pi}{4})$ ($1$ e $\\frac{\\sqrt{2}}{2}e^{\\frac{\\pi}{4}}$): 2 pontos\n\n# Notas:\n1. Se for evidente a intenção de determinar a derivada da função, a pontuação mínima a atribuir nesta etapa é 1 ponto.\n2. Se forem apresentados intervalos abertos em vez de fechados, a etapa é considerada cumprida.",
        "criterios_parciais": [
            {"pontos": 2, "descricao": "Determinar $g'(x)$"},
            {"pontos": 1, "descricao": "Escrever $g'(x) = 0$"},
            {"pontos": 2, "descricao": "Determinar o zero de $g'$"},
            {"pontos": 3, "descricao": "Quadro de sinal e monotonia"},
            {"pontos": 2, "descricao": "Intervalos de monotonia"},
            {"pontos": 2, "descricao": "Reconhecer que os extremos são $g(0)$ e $g(\\frac{\\pi}{4})$"},
            {"pontos": 2, "descricao": "Determinar $g(0)$ e $g(\\frac{\\pi}{4})$"}
        ],
        "status": "draft",
        "reviewed": True
    },
    {
        "id_item": "9.2",
        "cotacao_total": 14,
        "tipo": "open_response",
        "resposta_correta": None,
        "solucao": "Equacionar o problema ($g(x) = x$, ou equivalente): 3 pontos\nConsiderar a função $f$, definida por $f(x) = g(x) - x$: 3 pontos\nReferir que a função $f$ é contínua em $[\\frac{\\pi}{3}, \\frac{\\pi}{2}]$ (ver nota 1): 2 pontos\nDeterminar $f(\\frac{\\pi}{3})$: 1 ponto\nDeterminar $f(\\frac{\\pi}{2})$: 1 ponto\nConcluir que $f(\\frac{\\pi}{2}) < 0 < f(\\frac{\\pi}{3})$ (ou equivalente): 2 pontos\nConcluir o pretendido: 2 pontos\n\n# Notas:\n1. Se apenas for referido que a função $f$ é contínua, esta etapa é considerada como cumprida.",
        "criterios_parciais": [
            {"pontos": 3, "descricao": "Equacionar o problema ($g(x) = x$)"},
            {"pontos": 3, "descricao": "Considerar a função $f(x) = g(x) - x$"},
            {"pontos": 2, "descricao": "Referir que a função $f$ é contínua em $[\\frac{\\pi}{3}, \\frac{\\pi}{2}]$"},
            {"pontos": 1, "descricao": "Determinar $f(\\frac{\\pi}{3})$"},
            {"pontos": 1, "descricao": "Determinar $f(\\frac{\\pi}{2})$"},
            {"pontos": 2, "descricao": "Concluir que $f(\\frac{\\pi}{2}) < 0 < f(\\frac{\\pi}{3})$"},
            {"pontos": 2, "descricao": "Concluir o pretendido"}
        ],
        "status": "draft",
        "reviewed": True
    },
    {
        "id_item": "10",
        "cotacao_total": 14,
        "tipo": "open_response",
        "resposta_correta": None,
        "solucao": "Este item pode ser resolvido por, pelo menos, dois processos.\n\n# 1.º Processo\nObter $3e^x - 3e^{-x} = e^x + e^{-x}$: 3 pontos\nObter $2e^x - 4e^{-x} = 0$: 3 pontos\nObter $e^{2x} = 2$: 4 pontos\nObter a solução da equação ($\\frac{\\ln 2}{2}$, ou equivalente): 4 pontos\n\n# 2.º Processo\nObter $\\frac{e^{2x} - 1}{e^{2x} + 1} = \\frac{1}{3}$: 4 pontos\nObter $3e^{2x} - 3 = e^{2x} + 1$: 3 pontos\nObter $e^{2x} = 2$: 3 pontos\nObter a solução da equação ($\\frac{\\ln 2}{2}$, ou equivalente): 4 pontos",
        "criterios_parciais": [
            {"pontos": 3, "descricao": "Obter $3e^x - 3e^{-x} = e^x + e^{-x}$"},
            {"pontos": 3, "descricao": "Obter $2e^x - 4e^{-x} = 0$"},
            {"pontos": 4, "descricao": "Obter $e^{2x} = 2$"},
            {"pontos": 4, "descricao": "Obter a solução da equação ($\\frac{\\ln 2}{2}$)"}
        ],
        "status": "draft",
        "reviewed": True
    },
    {
        "id_item": "11",
        "cotacao_total": 14,
        "tipo": "open_response",
        "resposta_correta": None,
        "solucao": "Determinar o diâmetro da circunferência (6): 2 pontos\nApresentar a equação $d(t) = 6$ (ou equivalente) (ver nota 1): 4 pontos\nRepresentar o(s) gráfico(s) da(s) função(ões) visualizado(s) na calculadora que permite(m) resolver a equação (ver nota 2): 4 pontos\nAssinalar os pontos relevantes: 2 pontos\nApresentar os valores pedidos (1,4 s e 3,3 s): 2 pontos\n\n# Notas:\n1. Se não for apresentada qualquer equação, a pontuação a atribuir nesta etapa é 0 pontos.\n2. Se não for apresentado o referencial, a pontuação a atribuir nesta etapa é desvalorizada em 1 ponto.",
        "criterios_parciais": [
            {"pontos": 2, "descricao": "Determinar o diâmetro da circunferência (6)"},
            {"pontos": 4, "descricao": "Apresentar a equação $d(t) = 6$"},
            {"pontos": 4, "descricao": "Representar gráfico(s) na calculadora"},
            {"pontos": 2, "descricao": "Assinalar os pontos relevantes"},
            {"pontos": 2, "descricao": "Apresentar os valores pedidos (1,4 s e 3,3 s)"}
        ],
        "status": "draft",
        "reviewed": True
    },
    {
        "id_item": "12",
        "cotacao_total": 12,
        "tipo": "multiple_choice",
        "resposta_correta": "B",
        "solucao": "",
        "status": "draft",
        "texto_original": "Opção (B)",
        "reviewed": True
    },
    {
        "id_item": "13",
        "cotacao_total": 14,
        "tipo": "open_response",
        "resposta_correta": None,
        "solucao": "Este item pode ser resolvido por, pelo menos, dois processos.\n\n# 1.º Processo\nSubstituir $i^{23}$ por $-i$: 1 ponto\nObter $z_1 - i = -6i$: 1 ponto\nObter $-6i = 6e^{i\\frac{3\\pi}{2}}$ (ou equivalente): 1 ponto\nObter $z_2 = 2e^{i\\frac{4\\pi}{3}}$ (ou equivalente): 2 pontos\nObter um argumento de $z_2^n$ em função de $n$ (por exemplo, $\\frac{4n\\pi}{3}$): 1 ponto\nObter um argumento de $w$ em função de $n$ (por exemplo, $\\frac{3\\pi}{2} - \\frac{4n\\pi}{3}$): 2 pontos\nReconhecer que $w$ é um imaginário puro se $\\frac{3\\pi}{2} - \\frac{4n\\pi}{3} = \\frac{\\pi}{2} + k\\pi, k \\in \\mathbb{Z}$ (ou equivalente): 2 pontos\nObter $n = \\frac{3 - 3k}{4}, k \\in \\mathbb{Z}$ (ou equivalente): 2 pontos\nObter o valor pedido (3): 2 pontos\n\n# 2.º Processo\nSubstituir $i^{23}$ por $-i$: 1 ponto\nObter $z_1 - i = -6i$: 1 ponto\nReconhecer que $w$ é um imaginário puro se e somente se $z_2^n$ for um número real: 3 pontos\nObter $z_2 = 2e^{i\\frac{4\\pi}{3}}$ (ou equivalente): 2 pontos\nObter um argumento de $z_2^n$ em função de $n$ (por exemplo, $\\frac{4n\\pi}{3}$): 1 ponto\nReconhecer que $z_2^n$ é um número real se $\\frac{4n\\pi}{3} = k\\pi, k \\in \\mathbb{Z}$ (ou equivalente): 2 pontos\nObter $n = \\frac{3k}{4}, k \\in \\mathbb{Z}$ (ou equivalente): 2 pontos\nObter o valor pedido (3): 2 pontos",
        "criterios_parciais": [
            {"pontos": 1, "descricao": "Substituir $i^{23}$ por $-i$"},
            {"pontos": 1, "descricao": "Obter $z_1 - i = -6i$"},
            {"pontos": 1, "descricao": "Obter forma trigonométrica de $-6i$ ( $6e^{i\\frac{3\\pi}{2}}$ )"},
            {"pontos": 2, "descricao": "Obter forma trigonométrica de $z_2$ ( $2e^{i\\frac{4\\pi}{3}}$ )"},
            {"pontos": 1, "descricao": "Argumento de $z_2^n$ ( $\\frac{4n\\pi}{3}$ )"},
            {"pontos": 2, "descricao": "Argumento de $w$ ( $\\frac{3\\pi}{2} - \\frac{4n\\pi}{3}$ )"},
            {"pontos": 2, "descricao": "Condição para $w$ ser imaginário puro"},
            {"pontos": 2, "descricao": "Obter $n = \\frac{3 - 3k}{4}, k \\in \\mathbb{Z}$ (ou equivalente)"},
            {"pontos": 2, "descricao": "Obter o valor pedido (3)"}
        ],
        "status": "draft",
        "reviewed": True
    },
    {
        "id_item": "14",
        "cotacao_total": 14,
        "tipo": "open_response",
        "resposta_correta": None,
        "solucao": "Designemos por $x_1$ e $x_2$ as abcissas dos pontos $A$ e $B$, respetivamente. Reconhecer que as ordenadas dos pontos $A$ e $B$ são, respetivamente, $ax_1^2$ e $ax_2^2$: 2 pontos\nDeterminar $f'(x)$ (ver nota): 2 pontos\nObter uma equação da reta tangente ao gráfico da função $f$ no ponto $A$: 2 pontos\nObter uma equação da reta tangente ao gráfico da função $f$ no ponto $B$: 2 pontos\nObter a abcissa do ponto de intersecção das retas tangentes: 3 pontos\nReconhecer que a abcissa é o ponto médio das abcissas de A e B: 1 ponto\nConcluir o pretendido: 2 pontos\n\n# Nota:\nSe for evidente a intenção de determinar a derivada da função, a pontuação mínima a atribuir nesta etapa é 1 ponto.",
        "criterios_parciais": [
            {"pontos": 2, "descricao": "Reconhecer ordenadas $ax_1^2$ e $ax_2^2$"},
            {"pontos": 2, "descricao": "Determinar $f'(x)$"},
            {"pontos": 2, "descricao": "Obter equação da reta tangente em $A$"},
            {"pontos": 2, "descricao": "Obter equação da reta tangente em $B$"},
            {"pontos": 3, "descricao": "Obter a abcissa do ponto de intersecção"},
            {"pontos": 1, "descricao": "Reconhecer que a abcissa é o ponto médio"},
            {"pontos": 2, "descricao": "Concluir o pretendido"}
        ],
        "status": "draft",
        "reviewed": True
    }
]

output_path = "/Users/adrianoushinohama/Desktop/Exames Nacionais/workspace/EX-MatA635-EE-2023-CC-VD/criterios_raw.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(criterios, f, indent=2, ensure_ascii=False)

print(f"✅ Success: {output_path}")
