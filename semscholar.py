import requests
#from bs4 import BeautifulSoup
import json
from collections import deque
import pickle
import time
import os

# tor libs 
from stem import Signal
from stem.control import Controller

# yaml config
import confuse


config = confuse.Configuration('ScrappyScraper', __name__)
auth_password = config['tor']['password']

PAPER_ID = "f9ae5196908d21336ab02f5c20258dc760d125d6"

SIGNAL_SUCCESS = "success-signal"
SIGNAL_TOO_MANY_REQUESTS = "too-many-requests-signal"


LOAD_SET_NAME = "citation_set_final.pkl"
LOAD_QUEUE_NAME = "citation_queue_final.pkl"


LOOKUP_URL = "https://api.semanticscholar.org/v1/paper/"
"""
S2 Paper ID: LOOKUP_URL/<S2ID>
ArXiv ID: LOOKUP_URL/arXiv:<ARXIV_ID>
"""

class PaperNode:
	
	def __init__(self, paper_json):
		self.num_citations = len(paper_json["citations"])
		self.citationVelocity = paper_json["citationVelocity"]
		self.num_influential_citations = paper_json["influentialCitationCount"]

		self._id = paper_json["paperId"]
		self.title = paper_json["title"]
		self.authors = [author["name"] for author in paper_json["authors"]]
		self.year= paper_json["year"]
		self.abstract = paper_json["abstract"]

		self.citations = [citation["paperId"] for citation in paper_json["citations"]]



	def __str__(self):
		return f"ID: {self._id}\nTitle: {self.title}\nAuthors: {self.authors}\nNum citations: {self.num_citations}\nCitation velocity: {self.citationVelocity}\nNum influential citations: {self.num_influential_citations}\n"


	def __eq__(self, other):
		return self._id == other._id

	def __hash__(self):
		return hash(self._id)


class PaperGraph:

	def __init_(self, V):
		"""
		Args:
			V: number of vertices
		"""

		self.V = V
		self.graph = [None] * self.V
		
	def add_edge(self, src, dest):
		return None
	

def lookup_paper(id_s2, session):
	"""
	looks up paper specified by its semantic scholar paper id.
	then returns its json response to get request from ss api.

	Args:
		id_s2: semanticscholar paper id 
		session: requests session 

	Returns:
		json response to ss api call on given paper id
	"""	
	url = LOOKUP_URL + id_s2

	try:
		req = session.get(url)
		if req.status_code == requests.codes.ok:
			return req.json(), SIGNAL_SUCCESS

	except:
		print("reponse status code: ", end='', flush=True)
		print(req.status, flush=True)
		if req.status == requests.codes.too_many_requests:
			print("TOO MANY REQUESTS", flush=True)
			return _, SIGNAL_TOO_MANY_REQUESTS
		return _, SIGNAL_TOO_MANY_REQUESTS

def save_json(data):
	""" writes json data to outfile <paperId.json> """
	with open("%s.txt" % data["paperId"], "w") as out:
		json.dump(data, out)


def explore_citation(rootNode, session, citationset=None, citationqueue=None, limit=1000):
	
	# initialize set if not specified
	if citationset is None:
		print('initializing set')
		citationset = set() # empty set

	# initialize queue if not specified
	if citationqueue is None:
		print('initializing queue')
		citationqueue = deque([rootNode._id]) # set of paper ids
	
	print("Exploration limit: %d" % limit)

	i=0
	while(len(citationqueue) > 0 and i < limit):
		try:
			if i%100 == 0:
				print("i = %d" % i)
		
			# dequeue id
			paper_id = citationqueue.popleft()
			
			# find paper 
			data, signal = lookup_paper(paper_id, session)
			
			if signal == SIGNAL_TOO_MANY_REQUESTS:
				print("Too many requests (i=%d)" % i, flush=True)
				# renew connection and session
				renew_connection()
				session = get_tor_session()
				i-=1
				continue
			else:
				paperNode = PaperNode(data)
				#print(paperNode)

				# add to set
				citationset.add(paperNode)

				# add cited paper ids
				if paperNode.citations:
					for pid in paperNode.citations:
						citationqueue.append(pid)

				i+=1

		except Exception as e:
			print("Exception occurred")
			print(e)
			print("i: %d" % i)
			print("data: ", end="")
			print(data)
			print("signal: ")
			print(signal)
			print("paperNode: ", end="")
			print(paperNode)
	
	return citationset, citationqueue


def get_tor_session():
	"""
	returns a new tor requests session
	"""
	session = requests.session()

	session.proxies = {
		'http': 'socks5://localhost:9050', 
		'https': 'socks5://localhost:9050'
	}

	print("Session IP: %s" % session.get("https://httpbin.org/ip").text)

	return session


def renew_connection():
	print("renewing tor connection", end='')
	with Controller.from_port(port = 9051) as controller:
		print('.', end='')
		controller.authenticate(password=auth_password)
		print('.', end='')
		controller.signal(Signal.NEWNYM)
		print("renewed")


if __name__ == "__main__":
	
	# spawn tor session
	session = get_tor_session()
	
	paper_id = PAPER_ID
	data, _ = lookup_paper(paper_id, session)	
	
	root = PaperNode(data)
	print("##### Root Paper #####\n%s" % root)

	"""
	# load / init set, queue
	"""
	paper_set = None
	paper_queue = None

	print("### Loading set and queue..", end="")

	if os.path.exists(LOAD_SET_NAME) and os.path.exists(LOAD_QUEUE_NAME):

		# add to loaded set, queue
		with open(LOAD_SET_NAME, "rb") as fset, open(LOAD_QUEUE_NAME, "rb") as fqueue:
			paper_set = pickle.load(fset)
			paper_queue = pickle.load(fqueue)
			print("....LOADED")
		
		print("## loaded info ###")
		print("> set size: %d" % len(paper_set))
		print("> queue size: %d" % len(paper_queue))
	
	# explore 
	paper_set, paper_queue = explore_citation(root, session, paper_set, paper_queue)
	
	print("> %s papers explored" % len(paper_set))
	print("> Queue size: %d" % len(paper_queue))

	# add timestamp to pickle
	t = time.localtime()
	timestamp = time.strftime("%b-%d-%Y_%H%M", t)

	# pickle set
	with open("citation_set_%s.pkl" % timestamp, "wb") as out:
		pickle.dump(paper_set, out)
		print("set pickled")

	# pickle queue
	with open("citation_queue_%s.pkl" % timestamp, "wb") as out:
		pickle.dump(paper_queue, out)
		print("queue pickled")
	
	print("complete")
