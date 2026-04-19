import json

workspace_dir = "/Users/adrianoushinohama/Desktop/Exames Nacionais/Provas de portugues/workspace/EX-Port639-F1-2024_net"

# Enunciados from prova.md (cleaned)
text_a = "Leia o texto e as notas.\n\nTal como em outras obras do século XIX, também na novela Coração, Cabeça e Estômago se caricatura a sensibilidade e o modo de vida românticos. No excerto que vai ler, são visíveis as transformações operadas pelo protagonista com o intuito de se aproximar da imagem de um herói romântico.\n\nNa minha qualidade de cético, entendi que a desordem dos cabelos devia ser a imagem da minha alma. Comecei, pois, por dar à cabeça um ar fatal, que chamasse a atenção, e aguçasse a curiosidade dum mundo já gasto em admirar cabeças não vulgares. A anarquia dos meus cabelos custava-me dinheiro e muito trabalho. la, todos os dias, ao cabeleireiro\n5 calamistrar1 os longos anéis, que me ondeavam nas espáduas²; depois desfazia as espirais, riçava-as em caprichosas ondulações, dava à fronte o máximo espaço, e sacudia a cabeça para desmanchar as torcidas deletreadas³ da madeixa. Como quer, porém, que a testa fosse menos escampada4 que o preciso para significar «desordem e génio», comecei a barbear a testa, fazendo recuar o domínio do cabelo, a pouco e pouco, até que me criei uma fronte\n10 dilatada, e umas bossas frontais, como a natureza as não dera a Shakespeare nem a Goethe. A minha cara ajeitava-se pouco à expressão dum vivo tormento de alma, em virtude de ser uma cara sadia, avermelhada, e bem fornida de fibra musculosa. Era-me necessário remediar o infortúnio de ter saúde, sem atacar os órgãos essenciais da vida, mediante o uso de beberagens. Aconselharam-me os charutos do contrato5; fumei alguns dias, sem mais\n15 resultado que uma ameaça de tubérculos6, uma formal estupidez de espírito, e não sei que profundo dissabor até da farsa em que eu a mim próprio me estava dando em espetáculo. A cara mantinha-se na prosa ignóbil do escarlate, mais incendiada ainda pelos acessos de tosse, provocados pelo fumo. Um médico da minha íntima amizade receitou-me uma essência roixa7 com a qual eu devia pintar o que vulgarmente se diz «olheiras». Ao deitar-me,\n20 corria levemente algumas pinceladas sobre a cútisº, que desce da pálpebra inferior até às proeminências malares; ao erguer-me, tinha todo o cuidado em não lavar a porção arroixada pela tinta, e com uma maçaneta de algodão em rama desbastava a pintura nos pontos em que ela estivesse demasiadamente carregada. O artístico amor com que eu fazia isto deu em resultado uma tal perfeição no colorido, que até o próprio médico chegou a persuadir-se, de\n25 longe, que o pisado dos meus olhos era natural, e eu mesmo também me parece que cheguei à persuasão do médico.\n\nFiz, pois, de mim uma cara entre o sentimental de Antonyº e o trágico de Fausto10. Seria, no entanto, mais completa a minha satisfação se à raiz do cabelo, no ponto em que eu barbeava a cabeça para aumentar a testa, me não aparecesse um diadema11 azulado. Era a natureza a vingar-se.\n\n\n1 calamistrar - tornar crespo ou frisado.\n2 espáduas - ombros.\n3 deletreadas - repartidas.\n4 escampada - ampla; larga.\n5 charutos do contrato - charutos fabricados sob contrato com a Coroa, que detinha o monopólio deste produto.\n6 tubérculos - nódulos arredondados, nos pulmões, característicos da tuberculose.\n7 roixa - o mesmo que «roxa».\n8 cútis - pele da face.\n9 Antony… Fausto - referências a personagens protagonistas de dramas de Alexandre Dumas e de uma obra de Goethe, respetivamente, autores românticos.\n10 diadema - faixa semicircular no alto da testa.\n11 azulado - o mesmo que «azulada»."

poem_b = "Leia o poema.\n\nDepus a máscara e vi-me ao espelho…\nEra a criança de há quantos anos..\nNão tinha mudado nada..\n\nÉ essa a vantagem de saber tirar a máscara. 5 É-se sempre a criança, O passado que fica, A criança. Depus a máscara, e tornei a pô-la. Assim é melhor. 10 Assim sou a máscara.\n\nE volto à normalidade como a um términus de linha.\n\nÁlvaro de Campos, Poesia, edição de Teresa Rita Lopes, Lisboa, Assírio & Alvim, 2002, p. 514."

text_ii = "Leia o texto.\n\nA beleza pode ser consoladora, perturbadora, sagrada ou profana; pode revigorar, atrair, inspirar ou arrepiar. Pode afetar-nos de inúmeras maneiras. Todavia, nunca a olhamos com indiferença: a beleza exige visibilidade. Ela fala-nos diretamente, qual voz de um amigo íntimo. Se há pessoas indiferentes à beleza, é porque são, certamente, incapazes de a perceber.\n\nNo entanto, os juízos de beleza dizem respeito a questões de gosto e este pode não ter um fundamento racional. Mas, se for o caso, como explicar o lugar de relevo que a beleza ocupa nas nossas vidas e porque lamentamos o facto se disso se trata de a beleza estar a desaparecer do nosso mundo? Será verdade, como sugeriram tantos escritores e artistas desde Baudelaire a Nietzsche, que a beleza e a bondade podem divergir e que uma coisa pode ser bela precisamente por causa da sua imoralidade?\n\nAlém disso, uma vez que é natural que os gostos variem, como pode o gosto de uma pessoa servir de critério para aferir o de outra? Como é possível dizer, por exemplo, que um certo tipo de música é superior ou inferior a outro, se os juízos comparativos refletem apenas o gosto daquele que os faz?\n\nEste relativismo, hoje familiar, levou algumas pessoas a rejeitarem os juízos de beleza por serem puramente «subjetivos». Os gostos não se discutem, argumentam, pois, quando se critica um gosto, mais não se faz do que expressar um outro; assim sendo, nenhum ensinamento ou aprendizagem pode vir de uma «crítica». Esta atitude tem posto em questão muitas das disciplinas que tradicionalmente pertencem às humanidades. Os estudos de arte, música, literatura e arquitetura, libertados da disciplina imposta pelo juízo estético, dão a sensação de terem perdido a sustentação firme na tradição e na técnica, que tinha levado os nossos predecessores a considerarem-nos nucleares ao currículo. Daí a atual «crise das humanidades»: haverá alguma razão para estudar a nossa herança artística e cultural, se o juízo acerca da sua beleza é destituído de alicerces racionais? Ou, se resolvermos estudá-la, não deveria esse estudo ser feito com um espírito cético, questionando as suas pretensões ao estatuto de autoridade objetiva, desconstruindo a sua pose de transcendência?\n\nRogério Scruton, Beleza: Uma Muito Breve Introdução, trad. Carlos Marques, Lisboa, Guerra & Paz."

questoes = [
    {
        "id_item": "I-ctx",
        "tipo_item": "context_stem",
        "enunciado": "Apresente as suas respostas de forma bem estruturada.",
        "grupo": "I",
        "reviewed": True
    },
    {
        "id_item": "I-A-ctx",
        "tipo_item": "context_stem",
        "enunciado": text_a,
        "grupo": "I",
        "reviewed": True,
        "observacoes": ["[notas_rodape] [...]"]
    },
    {
        "id_item": "I-1",
        "tipo_item": "open_response",
        "enunciado": "Ao referir a «farsa em que eu a mim próprio me estava dando em espetáculo» (linha 16), o protagonista revela a sua intenção de criar uma imagem de si que não corresponde à realidade. Explicite em que consiste essa imagem.",
        "tema": "Narrativa",
        "subtema": "Coração, Cabeça e Estômago",
        "grupo": "I",
        "reviewed": True
    },
    {
        "id_item": "I-2",
        "tipo_item": "open_response",
        "enunciado": "O texto constitui um retrato humorístico do herói romântico. Refira dois aspetos significativos que evidenciem a dimensão cómica desse retrato.",
        "tema": "Narrativa",
        "subtema": "Coração, Cabeça e Estômago",
        "grupo": "I",
        "reviewed": True
    },
    {
        "id_item": "I-3",
        "tipo_item": "complete_table",
        "enunciado": "Complete as afirmações abaixo apresentadas, selecionando a opção adequada a cada espaço.\n\nNa folha de respostas, registe apenas as letras - a) e b) - e, para cada uma delas, o número que corresponde à opção selecionada.\n\nNo primeiro parágrafo, o narrador recorre a expressões como «Comecei» (linha 2), «todos os dias» (linha 4), «depois» (linha 5), «a pouco e pouco» (linha 9) e «até que» (linha 9) para a) No final do excerto, ao afirmar «Era a natureza a vingar-se.» (linhas 29 e 30), o narrador b)",
        "tema": "Gramática / Narrativa",
        "subtema": "Coração, Cabeça e Estômago",
        "grupo": "I",
        "reviewed": True,
        "imagens": ["imagens_extraidas/3642881736847c078955bef04dba4334bcea86b5ba588633257aa9dadd0a2057.jpg"],
        "pool_opcional": "pool_I_II_opcional"
    },
    {
        "id_item": "I-B-ctx",
        "tipo_item": "context_stem",
        "enunciado": poem_b,
        "grupo": "I",
        "reviewed": True
    },
    {
        "id_item": "I-4",
        "tipo_item": "open_response",
        "enunciado": "Explique a importância da máscara na construção da dualidade do sujeito poético, tal como é apresentada ao longo do poema.",
        "tema": "Poesia",
        "subtema": "Fernando Pessoa / Álvaro de Campos",
        "grupo": "I",
        "reviewed": True
    },
    {
        "id_item": "I-5",
        "tipo_item": "open_response",
        "enunciado": "Depois de tirar a máscara, o sujeito poético opta por tornar a pô-la.\n\nJustifique essa opção, com base em dois aspetos significativos.",
        "tema": "Poesia",
        "subtema": "Fernando Pessoa / Álvaro de Campos",
        "grupo": "I",
        "reviewed": True
    },
    {
        "id_item": "I-6",
        "tipo_item": "multi_select",
        "enunciado": "Considere as afirmações seguintes sobre o poema.\n\nI. O ato de se ver ao espelho sugere o desejo de autoconhecimento por parte do sujeito poético.\nII. O sujeito poético anseia voltar a viver o seu tempo de infância.\nIII. A coexistência de versos longos e de versos curtos contribui para o ritmo do poema.\nIV. O recurso às reticências, no verso 3, indicia a frustração sentida pelo sujeito poético.\nV. No texto, evidenciam-se características da linguagem poética de Álvaro de Campos, como a liberdade formal e o uso de anáforas.\n\nIdentifique as três afirmações verdadeiras.\n\nEscreva, na folha de respostas, os números que correspondem às afirmações selecionadas.",
        "tema": "Poesia",
        "subtema": "Fernando Pessoa / Álvaro de Campos",
        "grupo": "I",
        "reviewed": True,
        "pool_opcional": "pool_I_II_opcional"
    },
    {
        "id_item": "I-7",
        "tipo_item": "open_response",
        "enunciado": "Nos textos apresentados na Parte A e na Parte B desta prova, o protagonista, no primeiro caso, e o sujeito poético, no segundo caso, apresentam uma determinada imagem de si próprios.\n\nEscreva uma breve exposição na qual compare esses textos quanto às ideias expressas.\n\nA sua exposição deve incluir:\n\n\u2022 uma introdução ao tema;\n\u2022 um desenvolvimento no qual explicite um aspeto em que os textos se aproximam e um aspeto em que se distinguem quanto à imagem que cada sujeito de enunciação apresenta de si próprio;\n\u2022 uma conclusão adequada ao desenvolvimento do tema.",
        "tema": "Intertextualidade",
        "subtema": "Camilo Castelo Branco / Álvaro de Campos",
        "grupo": "I",
        "reviewed": True
    },
    {
        "id_item": "II-ctx",
        "tipo_item": "context_stem",
        "enunciado": text_ii,
        "grupo": "II",
        "reviewed": True
    },
    {
        "id_item": "II-1",
        "tipo_item": "multiple_choice",
        "enunciado": "Segundo o autor, é impossível ser indiferente à beleza,",
        "alternativas": [
            {"letra": "A", "texto": "sempre que quem a observa entende o que essa beleza comunica."},
            {"letra": "B", "texto": "pois está inequivocamente associada a valores reconhecidos pela sociedade."},
            {"letra": "C", "texto": "dado o seu carácter simultaneamente sagrado e profano."},
            {"letra": "D", "texto": "porque todos os seres humanos interpretam essa beleza da mesma maneira."}
        ],
        "tema": "Leitura / Argumentação",
        "subtema": "Beleza",
        "grupo": "II",
        "reviewed": True
    },
    {
        "id_item": "II-2",
        "tipo_item": "multiple_choice",
        "enunciado": "2. As interrogações utilizadas, no segundo e no terceiro parágrafos, constituem uma estratégia argumentativa que visa",
        "alternativas": [
            {"letra": "A", "texto": "exprimir as dúvidas do autor do texto."},
            {"letra": "B", "texto": "suscitar a reflexão sobre o tema abordado."},
            {"letra": "C", "texto": "embelezar estilisticamente o discurso."},
            {"letra": "D", "texto": "pôr em causa o conceito de beleza."}
        ],
        "tema": "Leitura / Argumentação",
        "subtema": "Beleza",
        "grupo": "II",
        "reviewed": True
    },
    {
        "id_item": "II-3",
        "tipo_item": "multiple_choice",
        "enunciado": "3. De acordo com o texto, a «atual \"crise das humanidades\"» (linhas 22 e 23) é motivada pela",
        "alternativas": [
            {"letra": "A", "texto": "rejeição do relativismo inerente aos juízos estéticos subjetivos."},
            {"letra": "B", "texto": "subjugação dos juízos de valor à herança artística e cultural."},
            {"letra": "C", "texto": "desvalorização do rigor crítico que deve reger o juízo estético."},
            {"letra": "D", "texto": "recusa do espírito cético que contesta o conceito de beleza."}
        ],
        "tema": "Leitura / Argumentação",
        "subtema": "Beleza",
        "grupo": "II",
        "reviewed": True,
        "pool_opcional": "pool_I_II_opcional"
    },
    {
        "id_item": "II-4",
        "tipo_item": "multiple_choice",
        "enunciado": "4. Nas expressões «qual voz de um amigo íntimo» (linha 3) e «alicerces racionais» (linha 24) está presente",
        "alternativas": [
            {"letra": "A", "texto": "uma metonímia, no primeiro caso, e uma hipérbole, no segundo caso."},
            {"letra": "B", "texto": "uma comparação, no primeiro caso, e uma metáfora, no segundo caso."},
            {"letra": "C", "texto": "uma comparação, no primeiro caso, e uma metonímia, no segundo caso."},
            {"letra": "D", "texto": "uma metonímia, no primeiro caso, e uma comparação, no segundo caso."}
        ],
        "tema": "Linguística / Recursos Expressivos",
        "subtema": "Beleza",
        "grupo": "II",
        "reviewed": True,
        "pool_opcional": "pool_I_II_opcional"
    },
    {
        "id_item": "II-5",
        "tipo_item": "multiple_choice",
        "enunciado": "5. Todos os vocábulos e expressões abaixo apresentados contribuem para a coesão interfrásica, exceto",
        "alternativas": [
            {"letra": "A", "texto": "a expressão «Além disso» (linha 11)."},
            {"letra": "B", "texto": "o vocábulo «Todavia» (linha 2)."},
            {"letra": "C", "texto": "a expressão «No entanto» (linha 5)."},
            {"letra": "D", "texto": "a expressão «Esta atitude» (linha 18)."}
        ],
        "tema": "Linguística / Coesão",
        "subtema": "Beleza",
        "grupo": "II",
        "reviewed": True
    },
    {
        "id_item": "II-6",
        "tipo_item": "multiple_choice",
        "enunciado": "6. Todos os constituintes sublinhados desempenham a função sintática de complemento do adjetivo, exceto em",
        "alternativas": [
            {"letra": "A", "texto": "«indiferentes à beleza» (linha 4)."},
            {"letra": "B", "texto": "«incapazes de a perceber» (linha 4)."},
            {"letra": "C", "texto": "«juízos de beleza» (linha 5)."},
            {"letra": "D", "texto": "«inferior a outro» (linha 13)."}
        ],
        "tema": "Linguística / Sintaxe",
        "subtema": "Beleza",
        "grupo": "II",
        "reviewed": True
    },
    {
        "id_item": "II-7",
        "tipo_item": "multiple_choice",
        "enunciado": "7. Os vocábulos «que», na linha 12 e na linha 19, são",
        "alternativas": [
            {"letra": "A", "texto": "um pronome, no primeiro caso, e uma conjunção, no segundo caso."},
            {"letra": "B", "texto": "pronomes, em ambos os casos."},
            {"letra": "C", "texto": "conjunções, em ambos os casos."},
            {"letra": "D", "texto": "uma conjunção, no primeiro caso, e um pronome, no segundo caso."}
        ],
        "tema": "Linguística / Morfologia",
        "subtema": "Beleza",
        "grupo": "II",
        "reviewed": True,
        "pool_opcional": "pool_I_II_opcional"
    },
    {
        "id_item": "III-1",
        "tipo_item": "essay",
        "enunciado": "Afirma-se, frequentemente, que as redes sociais são usadas pelas pessoas, quer para se mostrarem ao mundo, quer para se esconderem por detrás de uma imagem falsa, e que isso são formas igualmente questionáveis de comunicação.\n\nNum texto de opinião bem estruturado, com um mínimo de duzentas e um máximo de trezentas e cinquenta palavras, defenda uma perspetiva pessoal sobre a afirmação apresentada.\n\nNo seu texto:\nexplicite, de forma clara e pertinente, o seu ponto de vista, fundamentando-o em dois argumentos, cada um deles ilustrado com um exemplo significativo;\nutilize um discurso valorativo (juízo de valor explícito ou implícito).",
        "tema": "Redação",
        "subtema": "Redes Sociais",
        "grupo": "III",
        "reviewed": True,
        "palavras_min": 200,
        "palavras_max": 350
    }
]

# Merge with default fields
full_items = []
for q in questoes:
    item = {
        "id_item": "", "tipo_item": "", "enunciado": "", "alternativas": [],
        "tema": "", "subtema": "", "tags": [], "imagens": [],
        "resposta_correta": None, "observacoes": [], "enunciado_contexto_pai": "",
        "descricao_breve": "", "solucao": "", "grupo": "",
        "reviewed": False, "pool_opcional": "", "palavras_min": None, "palavras_max": None,
        "linhas_referenciadas": [], "parametros_classificacao": []
    }
    item.update(q)
    full_items.append(item)

with open(f"{workspace_dir}/questoes_review.json", "w", encoding="utf-8") as f:
    json.dump(full_items, f, indent=2, ensure_ascii=False)
