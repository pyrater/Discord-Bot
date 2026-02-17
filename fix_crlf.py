path = r"\\192.168.2.4\dockers\python\applications\tars\boot.sh"
with open(path, "rb") as f:
    content = f.read()

new_content = content.replace(b"\r\n", b"\n")

with open(path, "wb") as f:
    f.write(new_content)

print("Converted to LF")
