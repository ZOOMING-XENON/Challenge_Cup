def AI_analysis():
    from Deepseek import Deepseek
    from MachineLearning import MachineLearning
    import copy
    dict2 = MachineLearning()
    dict1 = Deepseek()
    dict = copy.deepcopy(dict2)
    for file in dict.keys():
        if dict[file] == '0' and dict1[file] == '1':
            dict[file] = '1'
    return dict
if __name__ == '__main__':
    print(AI_analysis())