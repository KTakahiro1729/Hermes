
from ipykernel.kernelbase import Kernel
import socket, json, logging, re, traceback, timeout_decorator



class IBpythonKernel(Kernel):
    implementation = 'IBPython'
    implementation_version = '1.0'
    language = 'python'
    language_version = '3.5'
    language_info = {'name': 'IBPython',
                     'mimetype': 'text/plain',
                     'extension': '.py'}
    banner = "Jupyter Kernel for Blender Python"
    hermes_host = "localhost"
    code_port = 8887
    multi_magic = dict([]) # magic:func(content)
    mono_magic = {"setport":"magic_setport", "getport":"magic_getport"}
    SOCKET_TIMEOUT = 0.5
    def do_execute(self, code, silent,
                   store_history=True,
                   user_expressions=None,
                   allow_stdin=False):
        no_magic_code = self.parse_magic(code)
        if no_magic_code is None:
            return {'status': 'error',
                    'execution_count':
                        self.execution_count,
                    'payload': [],
                    'user_expressions': {},
                   }
        if len(no_magic_code) == 0:
            return {'status': 'ok',
                    'execution_count':
                        self.execution_count,
                    'payload': [],
                    'user_expressions': {},
                   }

        address = (self.hermes_host, self.code_port)
        try:
            json_response = self.sendrecv_hermes(address, code)
        except timeout_decorator.TimeoutError:
            content = {
                "name": "stderr",
                "text": "Could not access to hermes code socket({0}:{1})".format(self.hermes_host, self.code_port)
            }
            self.send_response(self.iopub_socket,
                'stream', content)
            return {'status': 'error',
                    'execution_count':
                        self.execution_count,
                    'payload': [],
                    'user_expressions': {},
                   }
        response = json.loads(json_response)
        # raise Exception(type(response))

        # send response
        if not silent:
            # send output
            if response["out"]:
                content = {
                    "name": "stdout",
                    "text": response["out"]
                }
                self.send_response(self.iopub_socket,
                    'stream', content)

            # send exception
            if response["exc"]:
                content = {
                    "name": "stderr",
                    "text": response["exc"]
                }
                self.send_response(self.iopub_socket,
                    'stream', content)

            # send evaluation
            if response["evl"] is not None:
                content = {
                    "name": "stderr",
                    "data": {"text/plain":str(response["evl"])},
                    "execution_count":self.execution_count
                }
                self.send_response(self.iopub_socket,
                    'execute_result', content)


        return {'status': 'ok',
                'execution_count':
                    self.execution_count,
                'payload': [],
                'user_expressions': {},
               }
    def parse_magic(self, code):

        # two % magic (whole cell)
        if code.lstrip().startswith("%%"):
            pat = r"\s*%%(?P<magic>\S+)\s*(?P<content>[\s\S]*$)"
            match = re.match(pat, code)
            if match is None:
                return None
            gdict = match.groupdict()
            magic = gdict["magic"]
            content = gdict["content"]
            if magic not in self.multi_magic.keys():
                return self.send_wrong_magic_err("no such multi magic")
            try:
                return getattr(self,self.multi_magic[magic])(content)
            except:
                return self.send_wrong_magic_err(traceback.format_exc())

        # one % magic (single line)
        no_magic_code = ""
        for line in code.split("\n"):
            if not line.lstrip().startswith("%"):
                no_magic_code += "\n" + line
            else:
                pat = r"\s*%(?P<magic>\S+)[ ,\t]*(?P<content>.*$)"
                match = re.match(pat, line)
                if match is None:
                    return None
                gdict = match.groupdict()
                magic = gdict["magic"]
                content = gdict["content"]
                if magic not in self.mono_magic.keys():
                    return self.send_wrong_magic_err("no such monoline magic")
                try:
                    getattr(self,self.mono_magic[magic])(content)
                except:
                    return self.send_wrong_magic_err(traceback.format_exc())
        return no_magic_code
    @timeout_decorator.timeout(SOCKET_TIMEOUT)
    def sendrecv_hermes(self, address, code):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(code.encode("utf-8"),address)
        response = sock.recv(1024).decode("utf-8")
        sock.close()
        return response
    def send_wrong_magic_err(self,reason):
        content = {"name": "stderr", "text":"Wrong magic syntax: {0}".format(reason)}
        self.send_response(self.iopub_socket, "stream", content)
        return None
    def magic_setport(self, content):
        target, port = content.split()
        if target == "code":
            self.code_port = int(port)
            content = {
                "name": "stdout",
                "data": {"text/plain":"set hermes code port to: {0}".format(port)},
                "execution_count":self.execution_count
            }
            self.send_response(self.iopub_socket,
                'execute_result', content)
    def magic_getport(self, content):
        target = content.rstrip()
        if target == "code":
            content = {
                "name": "stdout",
                "data": {"text/plain":"hermes code port is: {0}".format(self.code_port)},
                "execution_count":self.execution_count
            }
            self.send_response(self.iopub_socket,
                'execute_result', content)
if __name__ == '__main__':
    from ipykernel.kernelapp import IPKernelApp
    IPKernelApp.launch_instance(
        kernel_class=IBpythonKernel)
