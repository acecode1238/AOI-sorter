import csv


def csv_converter(name_txt):
    #name new csv file
    length = len(name_txt)

    if name_txt[length-4:length] != ".txt":
        name_txt = name_txt + ".txt"
        name_csv = name_txt[:length] + ".csv"
    else:
        name_csv = name_txt[:length-4] + ".csv"

    with open(name_txt) as txt_file, open(name_csv, "w", newline='') as csv_file:
        #csv module write row by row to csv_file
        writer = csv.writer(csv_file)

        for row in txt_file:
            row = row.strip()

            columns = row.split("\t")

            writer.writerow(columns)

    return name_csv


def searchhist(searchword, name):
    #stores matched results in items list
    items = []

    with open(name) as file:
        #iterates lines in csv file
        for row in file:
            row = row.strip().split(",")
            wafer_name = row[1][1:] + " " + row[2][:len(row[2])-1]
            time = row[0]
        
            if searchword.lower() in wafer_name.lower():
                items.append((wafer_name, "  Time: ", time))

        return items
    
convert = input("Textfile name: ")
name = csv_converter(convert)

while True:

    searchword = input("Search: ")
    result = searchhist(searchword, name)

    print()
    for v in result:
        #joins tuple items
        print("".join(v))
        print()


