with open(r"\\192.168.2.4\dockers\python\applications\tars\boot.sh", "rb") as f:
    content = f.read()
    print(repr(content))
    if b"\r\n" in content:
        print("CRLF DETECTED")
    else:
        print("LF ONLY")
