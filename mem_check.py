#! /usr/bin/python

import subprocess, shlex, logging, sys, getopt, time
from subprocess import call
import socket

class check_mem_usage():
	def __init__(self, args=[]):
		self.server = False
		self.num_vf = 0
		self.mlnx_dev = 'mlx5_x'
		try:
			opts, args = \
			getopt.getopt(args,"hi:n:s:",["interface=", "num_vf=",
				"server"])
		except getopt.GetoptError:
			print 'mem_usage.py -i <interface> -n <num_vf> -s'
			sys.exit(2)
		for opt, arg in opts:
			if opt == '-h':
				print 'mem_usage.py -i <interface> -n <num_vf>'
				sys.exit()
			elif opt in ("-i", "--interface"):
				self.mlnx_dev = arg
			elif opt in ("-n", "--num_vf"):
				self.num_vf = int(arg)
			elif opt in ("-s", "--server"):
				self.server = True

		self.host = '192.168.100.2'
		self.port = 5000
		self.dmesg_file = "/tmp/page_usage"

		logging.basicConfig()
		self.logger = logging.getLogger("mem_usage")
		self.logger.setLevel(logging.DEBUG)
		if (self.server):
			self.server_init()
		else:
			self.client_init()

	def run_cmd(self, cmd):
		#args = shlex.split(cmd)
		return subprocess.check_output(cmd, shell=True)
		#process = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE)
		#output, error = process.communicate()
		#return output

	def query_free_mem(self):
		cmd = "vmstat -s"
		vmstat_output = self.run_cmd(cmd)
		lines = vmstat_output.splitlines()
		mem_used= lines[1].lstrip().split()[0]
		return mem_used

	def setup_vf(self):
		cmd_reset_vf = ("echo 0 > /sys/class/infiniband/" + self.mlnx_dev + "/device/mlx5_num_vfs")
		cmd_set_vf = ("echo "+ str(self.num_vf) + " > /sys/class/infiniband/" + self.mlnx_dev +
				"/device/mlx5_num_vfs")
		message = 'done'

		self.logger.debug("Reseting %s num of VF to 0", self.mlnx_dev)
		self.run_cmd(cmd_reset_vf)
		time.sleep(30)
		self.client_socket.send(message.encode())

		self.logger.debug("Setting %s num of VF to %d", self.mlnx_dev, self.num_vf)
		self.run_cmd(cmd_set_vf)
		time.sleep(5)
		self.client_socket.send(message.encode())

	def start_record_dmesg(self):
		self.run_cmd("echo 'module mlx5_core +p' > /sys/kernel/debug/dynamic_debug/control")
		self.run_cmd("dmesg -C")
		cmd = "dmesg -w > /tmp/page_usage &"
		self.logger.debug("Saving dmesg to /tmp/page_usage")
		self.run_cmd(cmd)

	def stop_record_dmesg(self):
		self.run_cmd("killall dmesg")

	def server_init(self):
		server_socket = socket.socket()
		server_socket.bind((self.host, self.port))
		self.logger.info("Waiting for connection...")
		server_socket.listen(2)
		self.server_conn, address = server_socket.accept()
		self.logger.info("Connection from: " + str(address))

	def server_wait_for_vf(self):
		self.logger.info("Waiting for host VF")
		while True:
			data = self.server_conn.recv(1024).decode()
			if data.lower().strip() == 'done':
			    break

	def server_bringup_rep(self):
		self.run_cmd("ifconfig rep0-1 up")
		time.sleep(3)
		self.logger.info("Bringup rep0-1")

	def client_init(self):
		self.client_socket = socket.socket()
		self.client_socket.connect((self.host, self.port))
		self.logger.info("Connected to: " + self.host + ":" + str(self.port))

	def run(self):
		if (self.server):
			# Wait for host VF to reset
			self.server_wait_for_vf()
			self.start_record_dmesg()
			mem_before = int(self.query_free_mem()) / 1024
			# Wait for host VF to setup
			self.server_wait_for_vf()
			self.server_bringup_rep()
			mem_after = int(self.query_free_mem()) / 1024
			self.stop_record_dmesg()
			self.server_conn.close()
			mem_used = abs(mem_after - mem_before)
			self.logger.info("Total Memory Usage: %d MB, before %d MB, after %d MB",
					mem_used, mem_before, mem_after)
		else:
			self.setup_vf()
			self.client_socket.close()
			self.logger.info("Set up %d VFs done.", self.num_vf)

if __name__ == "__main__":
	test = check_mem_usage(sys.argv[1:])
	test.run()
