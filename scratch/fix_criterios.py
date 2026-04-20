import json
import os

workspace_cc = "workspace/EX-Port639-F2-2024-CC-VD_net"

def main():
    new_data = []

    # Common CL description logic
    def get_cl_img(img_list):
        if not img_list: return ""
        return "\n\n".join([f"![]({img})" for img in img_list])

    # I-A-1
    desc1_1 = "Devem ser abordados dois dos tópicos seguintes, ou outros igualmente relevantes:\n\na opulência, evidenciada, por exemplo, nos materiais luxuosos dos utensílios («de tartaruga, marfim, prata, aço e madrepérola» ‒ ll. 4-5) colocados na mesa de toilette de Jacinto, «toda de cristal» (ll. 3-4)/nas «máquinas monumentais da Sala de Banho» (l. 15), como os duches com diferentes saídas de água/no espelho folheado a prata/nos biombos de Quioto de seda bordada;\n\no excessivo cuidado com a higiene diária de Jacinto, patente, por exemplo, na quantidade e na diversidade de escovas («largas», «estreitas» e «recurvas», «côncavas», «pontiagudas», «rijas», «macias» ‒ ll. 7-9) usadas pela personagem para pentear o cabelo («De todas, fielmente, como amo que não desdenha nenhum servo, se utilizava o meu Jacinto.» ‒ ll. 10-11)/no excesso de tempo dedicado à escovagem do cabelo («catorze minutos» ‒ l. 12)/na sequência de toalhas de diferentes materiais usadas para limpar as mãos;\n\na atração pelas inovações tecnológicas ao serviço do bem-estar do ser humano, como é o caso dos maquinismos presentes na Sala de Banho de Jacinto.\n\n• Aspetos de conteúdo e de estruturação do discurso (C-ED)"
    desc1_2 = "![](imagens_extraidas/775fa1a31d864c03b84aa8f98fe8d334b0a05b3bd7ffd611bce3cc0331d2c228.jpg)\n\n(Continua na página seguinte)\n\n![](imagens_extraidas/197832364987c7803ab4dc8486feefa0f15b6b02d2a812d982df5de794e5827b.jpg)\n\n• Aspetos de correção linguística (CL)\n\n![](imagens_extraidas/317ab81c1d9dacca3604df9b5c55fe6f94fe494a13af1a48949f2f342ec186f6.jpg)"
    
    new_data.append({
        "id_item": "I-A-1", "cotacao_total": 13, "tipo": "open_response",
        "solucao": desc1_1 + "\n\n" + desc1_2,
        "criterios_parciais": [{"pontos": 10, "descricao": desc1_1}, {"pontos": 3, "descricao": desc1_2}],
        "reviewed": True
    })

    # I-A-2
    desc2_1 = "Devem ser abordados dois dos tópicos seguintes, ou outros igualmente relevantes, um que evidencie um impacto positivo e outro que evidencie um impacto negativo da civilização em Jacinto:\n\npor um lado, a civilização permite a Jacinto usufruir dos prazeres proporcionados por um conjunto de inventos, que se dá ao luxo de ter em sua casa OU por um lado, Jacinto assume-se como um homem moderno, ao rodear-se dos inventos proporcionados pela civilização;\n\npor outro lado, a civilização, associada à cidade, prende-o a uma agenda recheada de eventos de carácter social (e inúteis), como ser presidente do clube da Espada e Alvo, que lhe provocam momentos de silenciosa revolta («frequentemente arremessava para o tapete, numa rebelião de homem livre, aquela agenda que o escravizava» ‒ ll. 33-34) OU por outro lado, o ritual quotidiano de preparação matinal provoca em Jacinto cansaço e saturação (l. 23).\n\n• Aspetos de conteúdo e de estruturação do discurso (C-ED)"
    desc2_2 = "![](imagens_extraidas/99160b2678940d6d4ad9377e9c8730db17fe91e48267e2facbba5523b73b0aaf.jpg)\n\n• Aspetos de correção linguística (CL)\n\n![](imagens_extraidas/328b41c1a80d199e8a6ce2945b42342d778d3a4d54ecd8fce3cd19300c64a260.jpg)"
    new_data.append({
        "id_item": "I-A-2", "cotacao_total": 13, "tipo": "open_response",
        "solucao": desc2_1 + "\n\n" + desc2_2,
        "criterios_parciais": [{"pontos": 10, "descricao": desc2_1}, {"pontos": 3, "descricao": desc2_2}],
        "reviewed": True
    })

    # I-A-3 (multi_select)
    new_data.append({
        "id_item": "I-A-3", "cotacao_total": 13, "tipo": "multi_select",
        "solucao": "Identificação das afirmações verdadeiras: I, II e IV.",
        "respostas_corretas": ["I", "II", "IV"],
        "criterios_parciais": [{"pontos": 13, "descricao": "Versão 1 ‒ I, II e IV\nVersão 2 ‒ II, III e V"}],
        "reviewed": True
    })

    # I-B-4
    desc4_1 = "Devem ser abordados os tópicos seguintes, ou outros igualmente relevantes:\n\n‒ as rosas representam a beleza e, simultaneamente, são comparáveis, na sua efemeridade, à vida humana (vv. 3 e 4);\n‒ o curso diurno do sol representa a duração da vida: para a rosa, um dia; para o ser humano, uma duração sempre limitada e efémera («O pouco que duramos» ‒ v. 12).\n\n• Aspetos de conteúdo e de estruturação do discurso (C-ED)"
    desc4_2 = "![](imagens_extraidas/38b054e101cd0ffa8ae00c0c8269390f3977b95a5465723dba499f6544cd1248.jpg)\n\n![](imagens_extraidas/8c4e7580779f3da97df62667fe6c23dfb369115ccc43ba2b4efa3475a2938ab3.jpg)\n\n• Aspetos de correção linguística (CL)\n\n![](imagens_extraidas/8b54be2cdb53b5f0d03ff77bab7f2e4ff085b0d4c60097b106b5c51dbdbd4555.jpg)"
    new_data.append({
        "id_item": "I-B-4", "cotacao_total": 13, "tipo": "open_response",
        "solucao": desc4_1 + "\n\n" + desc4_2,
        "criterios_parciais": [{"pontos": 10, "descricao": desc4_1}, {"pontos": 3, "descricao": desc4_2}],
        "reviewed": True
    })

    # I-B-5
    desc5_1 = "Face à constatação da efemeridade da vida, o sujeito poético aconselha Lídia a que, tal como ele próprio (e à semelhança das rosas dos «jardins de Adónis» ‒ v. 1):\n\n‒ viva o momento presente («Assim façamos nossa vida um dia» ‒ v. 9), de acordo com o princípio epicurista do carpe diem (único caminho para a felicidade e para a ausência de dor), assumindo uma atitude de indiferença face à passagem do tempo, num esforço de autodisciplina;\n‒ assuma uma atitude deliberada de aceitação da efemeridade da vida e da inevitabilidade da morte («há noite antes e após / O pouco que duramos» ‒ vv. 11-12).\n\n• Aspetos de conteúdo e de estruturação do discurso (C-ED)"
    desc5_2 = "![](imagens_extraidas/7e0a4854aaa8f463c2f15b0c2af2607185cdcdc33419450abc24b9cd564380f0.jpg)\n\n(Continua na página seguinte)\n\n![](imagens_extraidas/cf7d1ee7852218fccc9434923c05a943e31d04a0919a78027f7014699640fccb.jpg)\n\n• Aspetos de correção linguística (CL)\n\n![](imagens_extraidas/da114485604d1bccb24941991c073af99ea4cc70956d82aa4741b4b5e88edd04.jpg)"
    new_data.append({
        "id_item": "I-B-5", "cotacao_total": 13, "tipo": "open_response",
        "solucao": desc5_1 + "\n\n" + desc5_2,
        "criterios_parciais": [{"pontos": 10, "descricao": desc5_1}, {"pontos": 3, "descricao": desc5_2}],
        "reviewed": True
    })

    # I-B-6 (complete_table)
    new_data.append({
        "id_item": "I-B-6", "cotacao_total": 13, "tipo": "complete_table",
        "solucao": "a) \u2192 2; b) \u2192 2.",
        "respostas_corretas": ["2", "2"],
        "criterios_parciais": [{"pontos": 13, "descricao": "Versão 1 ‒ a) \u2192 2; b) \u2192 2\nVersão 2 ‒ a) \u2192 1; b) \u2192 3"}],
        "reviewed": True
    })

    # I-C-7 (exposição)
    desc7_1 = "Devem ser abordados dois dos tópicos seguintes, ou outros igualmente relevantes:\n\n‒ em ambos os casos, o espaço representado é o quarto de dormir, destacando-se elementos e objetos que habitualmente integram esse espaço, como é exemplo, no romance queirosiano, a mesa de toilette atulhada de utensílios e o espelho diante do qual Jacinto penteia o seu cabelo e, na pintura de Magritte, a cama, o guarda-fatos e o pente, representados na imagem;\n\n‒ em ambos os casos, verifica-se a excessiva valorização atribuída aos objetos usados no quotidiano, patente tanto no excerto de A Cidade e as Serras, por exemplo, na quantidade e diversidade de escovas usadas por Jacinto para pentear o cabelo diariamente, durante catorze minutos/na quantidade e diversidade de toalhas usadas por Jacinto para limpar as mãos (evidenciando o luxo e a futilidade), como na pintura de Magritte, através da representação desproporcionada de objetos como o pente, o pincel de barbear, o copo ou o fósforo relativamente à cama e ao guarda-fatos, sugerindo a ideia (evidenciada no título) de que os objetos podem ser, para as pessoas, os seus valores pessoais;\n\n‒ no romance queirosiano, é representado um espaço fechado para dentro do qual foram trazidas as maravilhas da civilização moderna (a tecnologia patente nas «máquinas monumentais da Sala de Banho» ‒ l. 15), enquanto, na pintura de Magritte, se observa um espaço que parece aberto ao exterior, através da representação de um céu (elemento natural) nas paredes internas do quarto;\n\n‒ no romance queirosiano, há uma grande quantidade e diversidade de objetos como se constata, por exemplo, na descrição das escovas de cabelo, enquanto na pintura de Magritte os objetos (apesar de sobredimensionados) se reduzem a um número muito limitado e a muito pouca diversidade.\n\n• Aspetos de conteúdo (C)"
    desc7_2 = "• Aspetos de estruturação do discurso (ED)\n\n![](imagens_extraidas/e55af9ef93068980700fda632f2b91ef8d1ee7b3b0f79f7c71405f40b23a4bd2.jpg)"
    desc7_3 = "• Aspetos de correção linguística (CL)\n\n![](imagens_extraidas/76c27cf48378f3df14a9d1286ca5d2414084da2a4c9efd0fff8e211cd817cd39.jpg)"
    new_data.append({
        "id_item": "I-C-7", "cotacao_total": 13, "tipo": "essay",
        "solucao": desc7_1 + "\n\n" + desc7_2 + "\n\n" + desc7_3,
        "criterios_parciais": [{"pontos": 8, "descricao": desc7_1}, {"pontos": 3, "descricao": desc7_2}, {"pontos": 2, "descricao": desc7_3}],
        "reviewed": True
    })

    # GRUPO II (MC)
    mc_answers = [("1", "C"), ("2", "D"), ("3", "A"), ("4", "D"), ("5", "C"), ("6", "B"), ("7", "C")]
    for it, ans in mc_answers:
        new_data.append({
            "id_item": f"II-{it}", "cotacao_total": 13, "tipo": "multiple_choice",
            "solucao": f"Opção ({ans})",
            "resposta_correta": ans,
            "criterios_parciais": [{"pontos": 13, "descricao": f"Opção ({ans})"}],
            "reviewed": True
        })

    # GRUPO III
    desc3_1 = "• Aspetos de estruturação temática e discursiva (ETD)\n\n# Parâmetro A: Género/Formato Textual\n\n![](imagens_extraidas/45fe265246aea8f101b3621c8ac97c19f694b6f338761b5749400e1a25662991.jpg)\n\n# Parâmetro C: Organização e Coesão Textuais\n\n![](imagens_extraidas/7aefd5e201c9557f1eb32dd0471f7958e22e9f017ae699edb857ba52895cea40.jpg)"
    desc3_2 = "• Aspetos de correção linguística (CL)\n\n![](imagens_extraidas/f88bcb58b58cd588696d90362bb89f712df3353c6aa78996721a9b47ec4a0e94.jpg)"
    new_data.append({
        "id_item": "III-1", "cotacao_total": 44, "tipo": "essay",
        "solucao": desc3_1 + "\n\n" + desc3_2,
        "criterios_parciais": [{"pontos": 30, "descricao": desc3_1}, {"pontos": 14, "descricao": desc3_2}],
        "reviewed": True
    })

    with open(os.path.join(workspace_cc, "criterios_raw.json"), "w") as f:
        json.dump(new_data, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    main()
