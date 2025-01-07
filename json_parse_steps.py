import json, sys

with open(sys.argv[1]) as f:
    data = json.load(f)
    pages = data["log"]["pages"]
    bt_data = data["log"]["_groupData"]
    entries = data["log"]["entries"]
    entry_data = []
    for entry in entries:

        entry_list = [
            entry.get("pageref", ""),
            entry.get("request").get("url"),
            entry.get("_stepref", ""),
            entry.get("_btref", ""),
        ]

        if entry_list not in entry_data:
            entry_data.append(entry_list)

    data2 = [
        {
            "pos": step.get("position"),
            "name": step.get("name"),
        }
        for step in bt_data
    ]

    for d in data2:
        for e in entry_data:
            if d["pos"] == e[3]:
                bt_name = d["name"]
                print(f"url: {e[1]} transaction: {bt_name}")
