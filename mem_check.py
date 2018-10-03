#! /usr/bin/python

import subprocess, shlex, logging, sys, getopt, time
from subprocess import call
import socket
import os.path

class check_mem_usage():
	def __init__(self, args=[]):
		self.server = False
		self.num_vf = 1
		self.mlnx_dev = 'mlx5_x'
		self.num_rules = 0
		self.rules_script = "./tc-batch-l2-random-rule.sh"
		try:
			opts, args = \
				getopt.getopt(args,"hi:n:s:r:",
					["interface=", "num_vf=", "server=", "num_rules="])
		except getopt.GetoptError:
			print 'mem_usage.py -i <interface> -n <num_vf> -s <0|1> -r <num_rules>'
			sys.exit(1)
		for opt, arg in opts:
			if opt == '-h':
				print 'mem_usage.py -i <interface> -n <num_vf> -s <0|1> -r <num_rules>'
				sys.exit()
			elif opt in ("-i", "--interface"):
				self.mlnx_dev = arg
			elif opt in ("-n", "--num_vf"):
				self.num_vf = int(arg)
			elif opt in ("-s", "--server"):
				self.server = bool(int(arg))
			elif opt in ("-r", "--num_rules"):
				self.num_rules= int(arg)

		self.host = '192.168.100.2'
		self.port = 5000
		self.dmesg_file = "/tmp/page_usage"
		self.page_file = "/tmp/give_page"

		logging.basicConfig()
		self.logger = logging.getLogger("mem_check")
		self.logger.setLevel(logging.DEBUG)

		if (self.num_rules == 0):
			if (self.server):
				self.server_init()
			else:
				self.client_init()
		else:
			if not os.path.exists(self.rules_script):
				self.logger.error("%d doesn't exist", rules_script)
				sys.exit(2)

	def find(self, substr, infile, outfile):
		with open(infile) as a, open(outfile, 'w') as b:
			for line in a:
				if substr in line:
					b.write(line)

	def find_count(self, substr, infile):
		count = 0
		with open(infile) as file:
			for line in file:
				words = line.split()
				count += int(words[words.index(substr) + 1].replace(",", ""))
		return count

	def end_connection(self):
		if (self.server):
			self.server_conn.close()
		else:
			self.client_socket.close()

	def run_cmd(self, cmd):
		#args = shlex.split(cmd)
		try:
			output = subprocess.check_output(cmd, shell=True)
		except subprocess.CalledProcessError as e:
			print e.output
			if (self.num_rules == 0):
				self.end_connection()
			sys.exit("cmd: " + cmd)
		return output

	def query_free_mem(self):
		cmd = "vmstat -s"
		vmstat_output = self.run_cmd(cmd)
		lines = vmstat_output.splitlines()
		mem_used= lines[1].lstrip().split()[0]
		return mem_used

	def setup_vf(self):
		cmd_current_vf = ("cat /sys/class/infiniband/" + self.mlnx_dev + "/device/mlx5_num_vfs")
		cmd_reset_vf = ("echo 0 > /sys/class/infiniband/" + self.mlnx_dev + "/device/mlx5_num_vfs")
		cmd_set_vf = ("echo "+ str(self.num_vf) + " > /sys/class/infiniband/" + self.mlnx_dev +
				"/device/mlx5_num_vfs")
		message = 'done'

		count = self.run_cmd(cmd_current_vf)
		self.logger.debug("%s has %d VF enabled", self.mlnx_dev, int(count))
		if (int(count) > 0):
			self.logger.debug("Reseting %s num of VF to 0", self.mlnx_dev)
			self.run_cmd(cmd_reset_vf)
			time.sleep(40)
		self.client_socket.send(message.encode())

		self.logger.debug("Setting %s num of VF to %d", self.mlnx_dev, self.num_vf)
		self.run_cmd(cmd_set_vf)
		time.sleep(5)
		self.client_socket.send(message.encode())

	def setup_rules(self):
		cmd_setup_rules = (self.rules_script + " " + self.mlnx_dev + " " + str(self.num_rules))
		self.run_cmd(cmd_setup_rules)
		time.sleep(3)

	def start_record_dmesg(self):
		self.run_cmd("echo 'module mlx5_core +p' > /sys/kernel/debug/dynamic_debug/control")
		self.run_cmd("dmesg -C")
		cmd = ("dmesg -w > " + self.dmesg_file + " &")
		self.logger.debug("Saving dmesg to %s", self.dmesg_file)
		self.run_cmd(cmd)

	def stop_record_dmesg(self):
		self.run_cmd("killall dmesg")
		self.run_cmd("echo 'module mlx5_core -p' > /sys/kernel/debug/dynamic_debug/control")

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

	def check_rep(self):
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

			self.find("give_pages", self.dmesg_file, self.page_file)
			page_used = self.find_count("npages", self.page_file)
			mem_used = abs(mem_after - mem_before)

			self.logger.info("-----------------------------------------")
			self.logger.info("\tMemory Usage Total:\t\t%d MB", mem_used)
			self.logger.debug("\t  Before:\t\t%d MB", mem_before)
			self.logger.debug("\t  After:\t\t%d MB", mem_after)
			self.logger.info("\tPage Usage Total:\t\t%d", page_used)
			self.logger.info("-----------------------------------------")
		else:
			self.setup_vf()
			self.client_socket.close()
			self.logger.info("Set up %d VFs done.", self.num_vf)

	def check_rules(self):
		self.logger.info("Check mem usage of ovs rules")
		mem_before = int(self.query_free_mem()) / 1024
		self.setup_rules()
		mem_after = int(self.query_free_mem()) / 1024
		mem_used = abs(mem_after - mem_before)

		self.logger.info("-----------------------------------------")
		self.logger.info("\tMemory Usage Total:\t\t%d MB", mem_used)
		self.logger.debug("\t  Before:\t\t%d MB", mem_before)
		self.logger.debug("\t  After:\t\t%d MB", mem_after)
		self.logger.info("-----------------------------------------")

	def run(self):
		if (self.num_rules):
			self.check_rules()
		else:
			self.check_rep()

if __name__ == "__main__":
	test = check_mem_usage(sys.argv[1:])
	test.run()
