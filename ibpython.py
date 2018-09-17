
from ipykernel.kernelbase import Kernel
import socket, json, logging


def sendrecv_blender(address, code):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(code.encode("utf-8"),address)
    response = sock.recv(1024).decode("utf-8")
    sock.close()
    return response

class IBpythonKernel(Kernel):
    implementation = 'IBPython'
    implementation_version = '1.0'
    language = 'python'
    language_version = '3.5'
    language_info = {'name': 'IBPython',
                     'mimetype': 'text/plain',
                     'extension': '.py'}
    banner = "Jupyter Kernel for Blender Python"
    blender_address = ("localhost", 8887)
    def do_execute(self, code, silent,
                   store_history=True,
                   user_expressions=None,
                   allow_stdin=False):
        json_response = sendrecv_blender(self.blender_address, code)
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
            if response["evl"]:
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
if __name__ == '__main__':
    from ipykernel.kernelapp import IPKernelApp
    IPKernelApp.launch_instance(
        kernel_class=IBpythonKernel)
