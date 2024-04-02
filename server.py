#!/usr/bin/python3

#
# PDFMERGE
# Copyright (C) 2023 Adam Williams <broadcast at earthling dot net>
# 
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
# 



from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import sys
import subprocess
import json
import socket

ports = [ 8080, 8081, 8082, 8083, 8084, 8085, 8086, 8087, 8088, 8089, 8090 ]
port = ports[0]
HOSTNAME = 'localhost'
PROGRAM = 'PDFMerge'
def get_redirect_uri():
    return "http://" + HOSTNAME + ":" + str(port)

# config dictionary
config = { }

# the project file
project_path = ""
# the latest saved project
project_data = bytes()
access_token = ""

# the undo stack
undo_stack = []
redo_stack = []
current_undo = -1

# save the project file to disk
def save():
    with open(project_path, 'wb') as file:
        file.write(project_data)
        file.close()

# load the project file
def load():
    print("load project_path=%s" % project_path)
    with open(project_path, 'rb') as file:
        global project_data
        project_data = file.read()
        file.close()
    print("load data=%s" % project_data.decode("utf-8"))
    parse_project(project_data)

# returns if it is a new undo buffer
def parse_project(data):
    is_undo = False;
# extract the undo type
    lines = data.decode('utf-8').split("\n")
    for line in lines:
#        print("parse_project: line=" + line)
        values = line.split(" ")
        if values[0] == "UNDO":
            is_undo = (values[1].lower() == "true")
            print("parse_project: undo=" + str(is_undo))
            break
    return is_undo

def save_undo(data):
    global current_undo
    global undo_stack
    global redo_stack

    if current_undo < len(undo_stack):
        # drop from current undo to end
        if current_undo <= 0:
            undo_stack = []
            redo_stack = []
        else:
            undo_stack = undo_stack[0:current_undo]
            redo_stack = redo_stack[0:current_undo]
    # append the current buffer
    undo_stack.append(data)
    current_undo = len(undo_stack) - 1
    print("save_undo undos=%d redos=%d current_undo=%d" % 
        (len(undo_stack), len(redo_stack), current_undo))

def save_redo(data):
    global current_undo
    global undo_stack
    global redo_stack
    if len(undo_stack) > 0:
# create new redo level
        if len(redo_stack) < len(undo_stack):
            redo_stack.append(data)
            current_undo = len(redo_stack)
        else:
# replace last redo level in case it was a save without an undo
            redo_stack[len(redo_stack) - 1] = data
        print("save_redo undos=%d redos=%d current_undo=%d" % 
            (len(undo_stack), len(redo_stack), current_undo))

class MyServer(BaseHTTPRequestHandler):
    def content_type(self, path):
        if path.endswith(".js"):
            return "application/javascript"
        elif path.endswith(".html") or path.endswith(".htm"):
            return "text/html"
        elif path.endswith(".txt") or path.endswith(".java"):
            return "text/plain"
        elif path.endswith(".gif"):
            return "image/gif"
        elif path.endswith(".class"):
            return "application/octet-stream"
        elif path.endswith(".jpg") or path.endswith(".jpeg"):
            return "image/jpeg"
        else:
            return "text/plain"



    def send_file(self, path):
        self.send_response(200)
        self.send_header("Content-type", self.content_type(path))
        self.end_headers()
        try:
            file = open(path, 'rb')
        except FileNotFoundError:
            print("send_file: Couldn't open %s" % path)
        else:
            with file:
                data = file.read()
                self.wfile.write(data)
                file.close()
        
    def send_text(self, text):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.wfile.write(text.encode('utf-8'))
        
    def send_data(self, text):
        self.send_response(200)
        self.send_header("Content-type", "application/octet-stream")
        self.wfile.write(text)
        
    def errorReport(self, code, title, msg):
        self.send_response(code)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        string = "HTTP/1.0 " + str(code) + " " + title + "\r\n" + \
            "\r\n" + \
            "<!DOCTYPE HTML PUBLIC \"-//IETF//DTD HTML 2.0//EN\">\r\n" + \
            "<TITLE>" + str(code) + " " + title + "</TITLE>\r\n" + \
            "</HEAD><BODY>\r\n" + \
            "<H1>" + title + "</H1>\r\n" + msg + "<P>\r\n" + \
            "<HR><ADDRESS>" + PROGRAM + " at " + \
            HOSTNAME + \
            " Port " + str(port) + "</ADDRESS>\r\n" + \
            "</BODY></HTML>\r\n"
        self.wfile.write(string.encode('utf-8'));




    def do_GET(self):
        global current_undo
        global undo_stack
        global redo_stack
        path2 = self.path
# strip leading /
        if path2.startswith('/'):
            path2 = path2[1:]
#        print("do_GET path2=" + path2)
# extract arguments
        if "?" in path2:
            offset = path2.find("?")
            args = path2[offset + 1:]
# strip the arguments
            path2 = path2[0:offset]
#            print("do_GET args=" + args)
            args = args.split("&");
# make dictionary from the args
            arg_dict = {}
#            print("do_GET args=%d" % len(args))
            for arg in args:
#                print("do_GET arg=" + arg)
                offset = arg.find("=")
                if offset > 0:
                    arg_dict.update({arg[0:offset]: arg[offset + 1:]})
                else:
                    arg_dict.update({arg: ""})

# handle commands
        if path2 == "get_config":
# config value
#            print("do_GET get_config key=" + args[0] + " value=" + config[args[0]])
            self.send_text(config[args[0]])



        elif path2 == "load":
            self.send_text("PATH " + project_path + "\n")
            print("do_GET load data=" + project_data.decode("utf-8"));
            self.send_data(project_data)


        elif path2 == "undo":
            if current_undo > 0:
                current_undo -= 1
                self.send_data(undo_stack[current_undo])
            else:
                self.send_data(bytes("EMPTY", "utf-8"))
            print("do_GET undo undos=%d redos=%d current_undo=%d" % 
                (len(undo_stack), len(redo_stack), current_undo))

        elif path2 == "redo":
            if current_undo < len(redo_stack):
                self.send_data(redo_stack[current_undo])
                current_undo += 1
            else:
                self.send_data(bytes("EMPTY", "utf-8"))
            print("do_GET redo undos=%d redos=%d current_undo=%d" % 
                (len(undo_stack), len(redo_stack), current_undo))

        elif path2 == "get_pdf":
            print("do_GET get_pdf path=" + arg_dict["path"])
            self.send_file(arg_dict["path"])


        elif path2 == "get_tokens":
# token from authorization code
# run the curl command
            data = "code=" + arg_dict["code"] + \
                    "&client_id=" + config["CLIENT_ID"] + \
                    "&client_secret=" + config["CLIENT_SECRET"] + \
                    "&redirect_uri=" + get_redirect_uri() + \
                    "&grant_type=authorization_code"
            print("do_GET get_tokens data=" + data)
            text = subprocess.check_output(["curl", 
                "-s", 
                "--request", "POST",
                "--data", data,
                config["TOKEN_URI"]])
            print("do_GET get_tokens response=" + text.decode('utf-8'))
            response_dict = json.loads(text.decode('utf-8'))
# store the access token on the server
            global access_token
            access_token = response_dict["access_token"]
            self.wfile.write(bytes("OK", "utf-8"))
#            self.wfile.write(bytes("ACCESS_TOKEN %s" % response_dict["access_token"], "utf-8"))


        elif path2 == "get_cell":
# go to the consent prompt
            if access_token == "":
                print("do_GET get_cell access_token not set")
                self.send_text("__LOGIN")
            else:
# using OATH
                print("do_GET get_cell path=" + self.path)
                data = "https://sheets.googleapis.com/v4/spreadsheets/" + \
                    arg_dict["sheet"] + \
                    "/values/" + \
                    arg_dict["range"]
                print("do_GET get_cell data=" + data)
                text = subprocess.check_output(["curl", 
                    "-X", "GET", 
                    "-H", "Authorization: Bearer " + access_token, 
                    "-H", "Content-Type: application/json", 
                    data])
                print("do_GET get_cell response=" + text.decode('utf-8'))
                response_dict = json.loads(text.decode('utf-8'))
                if "values" in response_dict:
                    print("do_GET get_cell json=" + response_dict["values"][0][0])
                    value = response_dict["values"][0][0]
                    self.send_text(value)
                elif "range" in response_dict and "majorDimension" in response_dict:
# can get here if a cell is blank
                    self.send_text("BLANK")
                else:
# go to the consent prompt
                    self.send_text("__LOGIN")



        else:
# convert the path
            if path2 == '':
                path2 = 'index.html'

#           print("go_GET path2=%s" % path2)
# test existence of file
            if os.path.exists(path2):
                self.send_file(path2)
            else:
                self.errorReport(404, 'Not found', self.path)









# POST handler
    def do_POST(self):
        print("do_POST requestline=%s" % (self.requestline))
        print("path=\n%s" % (self.path))
        print("headers=%s" % (self.headers))
        lines = self.headers.as_string().split('\n')


        if self.path == "/save":
            size = 0
            for line in lines:
                if line.startswith("Content-Length:"):
                    values = line.split(' ')
                    size = int(values[1])
                    new_data = self.rfile.read(size)
                    print("do_POST save new_data=\n" + new_data.decode('utf-8'))
                    break

# extract the undo type
            if not parse_project(new_data):
# not an undo buffer.  save the data to disk & the redo buffer
                global project_data
                project_data = new_data
                save()
                save_redo(new_data)
            else:
# save an undo buffer
                save_undo(new_data)
        else:
            GET_KEY = 0
            GET_TEXT = 1
            GET_DATA = 2
            state = GET_KEY

# get the boundary
            for line in lines:
                if line.startswith("Content-Type:"):
                    strings = line.split("boundary=")
                    if len(strings) > 1:
                        boundary = strings[1]
    #                    print("boundary=" + boundary)
                        break

            key = ""
            value = ""
            keyvalues = {}

            done = False
            skip = 0
    # extract dictionary from the POST request
            while not done:
                data = self.rfile.readline()
    # skip a line
                if skip > 0:
                    skip -= 1
                    continue

                if state == GET_KEY:
                    line = data.decode('utf-8')

                    print("GET_KEY line=%s" % line)
                    if boundary + "--" in line:
                        done = True
                    elif line.startswith("Content-Disposition:"):
                        strings = line.split("\"")
                        if len(strings) > 1:
                            key = strings[1]
                            print("GET_KEY key=%s" % key)
    # get text or data based on the key
                            if key == "NEW_NAME" or \
                                key == "MKDIR":
                                state = GET_TEXT
                                skip = 1
                            else:
                                print("unknown data")
                elif state == GET_TEXT:
                    line = data.decode('utf-8')
                    print("GET_TEXT line=%s" % line)
    # strip trailing \n
                    morelines = line.split("\n")
                    keyvalues.update({key: morelines[0]})
                    state = GET_KEY

            print("POST dictionary:")
            for key, value in keyvalues.items():
                print("%s: %s" % (key, value))

# send response page
        self.wfile.write(bytes("<p>SUCCESS</p>", "utf-8"))










if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage %s <project file>" % sys.argv[0])
        print("Example: %s form" % sys.argv[0])
        exit()
        
    print("Welcome to %s" % PROGRAM)
    project_path = sys.argv[1]

    for i in range(len(ports)):
        port = ports[i];
        server = None
        try:
            server = HTTPServer((HOSTNAME, port), MyServer)
        except socket.error:
            pass
        if server != None:
            break

    if server == None:
        print("No more ports available")
        exit()

# load the project file
    if os.path.exists(project_path):
        print("Reading %s" % project_path)
        load()
    else:
        print("Creating %s" % project_path)

# load config file
    print("Loading config file")
    file = open("pdfmerge.conf", "r")
    while True:
        line = file.readline()
        if line == "":
            break
        line = line.strip()
        if line.startswith("#") or line == "":
            continue
        index = line.find(" ")
        if index > 0:
            config.update({line[0:index]: line[index + 1:]})
    file.close()

# print it
#    for key, value in config.items():
#        print("    %s: %s" % (key, value))


    print("Go to http://%s:%d to use the program.\n" % (HOSTNAME, port))

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

    server.server_close()
    print("Server stopped.")

