#!/usr/local/bin/python2.3
""" BLumbox - Bloglines to MBOX Tool

Welcome to BLumbox
------------------

BLumbox is short for Bloglines to MBOX.  This is a tool designed to
retreive RSS feeds as subscribed to via Bloglines and store them in an
MBOX style mailbox which is suitable for reading via IMAP or your mail
application of choice.

BLumbox is designed to be run via cron at regular intervals...1 hour
minimum recommended, 2 hours probably ideal.

If your a Maildir instead of an MBOX sorta person, see
http://batleth.sapienti-sat.org/projects/mb2md/ for a perl conversion
script

Requirements
------------

Python version 2.3 or greater.  See http://www.python.org/
Feedparser version 3.3 or greater.  See http://www.feedparser.org/

Installation
------------

Uncompress and untar in a directory of your choice.  Using GNU tar:
   # tar -zxf blumbox-<version>.tar.gz

Precautions
-----------

What if Bloglines turns evil?  Simple, keep a copy of your blog
subscriptions in OPML format.

Visit this link (substitute your bloglines userid) and save the
resulting OPML file.

   http://www.bloglines.com/export?id=userid

You can easily import that file into any number of aggregator
applications.

Configuration
-------------

Edit 'blumbox.py' and set your Blogines userid and password, also your
email directory path as appropriate in the 'User Configuration' section
(see below).

Additionally, be sure to modify the first line to point to the correct
location of your Python interpreter (see above).

Execution
---------

For the initial run, it is recommended to run it by hand using the
following commands:

   # cd blumbox
   # ./blumbox.py

Subsequent runs should be scheduled as a cron job.  The following entry
may be used to execute blumbox hourly:

   0 * * * * /path/to/blumbox/blumbox.py

Known Bugs
----------

None.

Unknown Bugs
------------

Probably several.
"""

__version__ = "1.2"
__date__ = "11/27/2004"
__author__ = "James E. Robinson, III  (james@robinsonhouse.com)"
__copyright__ = "Copyright 2004, James E. Robinson, III"
__license__ = "BSD"
__credits__ = ""
__contributors__ = ""

__history__ = """
1.2 - JER - 11/27/2004
   - added back md5 to import list

1.1 - JER - 11/24/2004
   - public release, few documention issues

1.0 - JER - 11/23/2004
   - based on SynGen 1.5 dated 10/05/2004
"""

"""
Bloglines API Basics 

http://www.bloglines.com/export?id=userid
Response: OPML only

http://rpc.bloglines.com/update?user=userid@example.com&ver=1
Response: |A|B|  a=unread count, b=unused

http://rpc.bloglines.com/listsubs (BasicAuth)
Response: OPML with bloglines info

http://rpc.bloglines.com/getitems (BasicAuth)
Options:
   s - subid, from listsubs above
   n - mark read, vals=1,0
Response: RSS 2.0 feed for subid
"""
import os
HOME = os.environ.get('HOME')    # Users home directory

# User Configuration ---------------------------------------------------

# Bloglines User Information:
BLOGUSER = 'you@example.com' # an email address
BLOGPASS = 'password' # yep, password

# Should Bloglines mark retrieved articles as read?
# Set to False for testing
BLMARKREAD = True

# directory to create/update mbox files, must already exist
# default: ~/mail/Offline
MAILDIR = HOME + "/mail/Offline"

# End User Configuration -----------------------------------------------

_DEBUG = 0

# system libraries
import sys, traceback, fcntl, string, time, re, base64, md5
import email.Message, urllib2, urllib, xml.sax, xml.sax.saxutils

# external libraries
try:
   import feedparser
except:
   print "Unable to import module FeedParser.  For download information"
   print "please see: http://www.feedparser.org/ for latest"
   sys.exit(1)

BLOPMLURL = 'http://rpc.bloglines.com/listsubs'

if BLMARKREAD:
   BLFEEDURL = 'http://rpc.bloglines.com/getitems?n=1&s='
else:
   BLFEEDURL = 'http://rpc.bloglines.com/getitems?n=0&s='

# System Configuration -------------------------------------------------

CURTIME = time.asctime(time.gmtime())

ENTITY_DICT = { '&apos;': "'", '&acirc;': "'", '&amp;': '&',
               '&quot;': '"', '&nbsp;': " ",
               '&rdquo;': '"', '&ldquo;': '"', 
               '&rsquo;': "'", '&lsquo;': "'" }

# security settings for file creation
os.umask(077)

# Authentication string for Bloglines service
BASICAUTH = base64.encodestring('%s:%s' % (BLOGUSER, BLOGPASS))[:-1]

# Bloglines Utilities -------------------------------------------------

class OPMLHandler(xml.sax.ContentHandler):
   """
   A SAX content handler that turns an OPML subscription list into a
   dictionary indexed by Bloglines subid
   """
   def startDocument(self):
      self.data = {}
      self.folder = ""
      
   def startElement(self,tag,attributes):
      if tag == 'outline':
         if attributes.has_key('xmlUrl'):
            if int(attributes['BloglinesUnread']) > 0:
               self.data[attributes['BloglinesSubId']] = self.folder
         else:
            self.folder = 'in_' + attributes['title'].lower()
         
def getBLdata(subid):
   """
   args: subid - BL subid used to retrieve RSS data
   output: none
   result: valid RSS in xml format
   """

   # Form the request
   url = BLFEEDURL + subid
   req = urllib2.Request(url)
   req.add_header("Authorization", "Basic %s" % BASICAUTH)

   f = urllib2.urlopen(req)
   xml = f.read()
   f.close()

   return xml

def getBLfeeds(xmlUrl):
   """
   args: xmlUrl - location of user subscriptions in OPML format
   output: none
   result: dictionary from parsed OPML
   """
   # Build parser      
   parser = xml.sax.make_parser()
   parser.setContentHandler(OPMLHandler())

   # Form request
   req = urllib2.Request(xmlUrl)
   req.add_header("Authorization", "Basic %s" % BASICAUTH)

   f = urllib2.urlopen(req)

   BUFSIZE = 8192
   
   # feed the retrieved opml file to the parser a chunk at a time
   while True:
      data = f.read(BUFSIZE)
      if not data: break
      parser.feed(data)

   f.close()

   # just the data ma'am
   return parser._cont_handler.data

# System Utilities -----------------------------------------------------

def _debuglog(message):
   if _DEBUG: print message
   return

def formatExceptionInfo(maxTBlevel=5):
   """
   args: maxTBlevel, default 5 - max levels for trackback information
   output: none
   returns: string with exception name, arguments and trackback info
   """

   cla, exc, trbk = sys.exc_info()
   excName = cla.__name__

   try:
      excArgs = exc.__dict__["args"]
   except KeyError:
      excArgs = "<no args>"

   excTb = traceback.format_tb(trbk, maxTBlevel)

   return excName + str(excArgs) + str(excTb)

# String Utilities -----------------------------------------------------

def stripHtmlTags(text):
   """
   args: text - string
   output: none
   returns: string with all tags removed
   """

   result = xml.sax.saxutils.unescape(text, ENTITY_DICT)
   zapTagsRe = re.compile('<.+?>')
   result = re.sub(zapTagsRe, '', result)
   return result

def stripNewlines(text):
   """
   args: text - string
   output: none
   returns: string with all newlines replaced with spaces
   """

   zapNewlinesRe = re.compile(r'(\n+|\r+)')
   result = re.sub(zapNewlinesRe, ' ', text)
   return result

def firstNwords(text, count=7):
   """
   args: text - string
         count - number of words max
   output: none
   returns: string with up to count words of the original text
   """

   expr = '(.+?\s+){1,%d}' % count
   fewWordsRe = re.compile(expr)
   few = fewWordsRe.search(text)
   if few != None:
      result = stripNewlines(few.group(0))
   else:
      result = text
   return result

# Mailbox Utilities ----------------------------------------------------

def writeMailbox(mbox, data):
   """
   args: mbox - filename
         data - text for output in MBOX format
   output: to file mbox
   returns: none / raise exception
   """

   fp = file(mbox, 'a')
   fd = fp.fileno()
   fcntl.lockf(fd, fcntl.LOCK_EX)
   fp.write(data)
   fcntl.lockf(fd, fcntl.LOCK_UN)
   fp.close()
   return

# RSS Processing Functions ---------------------------------------------

def reportFeedError(detail, url, mbox):
   """
   args: detail - detail string of error
         url - RSS url 
         mbox - name of mailbox
   output: none
   returns: none / raise exception
   """

   validate = urllib.quote(url)
   detail = str(detail)

   msg = email.Message.Message()
   msg.set_unixfrom('From BLuMBOX@SynGen.rss ' + CURTIME)
   msg.add_header('From', '"BLuMBOX RSS Aggregator" <BLuMBOX@SynGen.rss>')
   msg.add_header('To', '"RSS eMail Reader" <MBOX@SynGen.rss>')
   msg.add_header('Subject', 'Error in RSS Feed')
   msg.add_header('Message-ID', '<' + url + '@feederror.syngen.rss>')
   msg.add_header('Date', CURTIME)
   msg.set_type('text/plain')
   msg.set_charset('iso-8859-1')
   msg.epilogue = ''
   payload = 'Problem parsing XML feed data.\n' + \
            'Feed URL: ' + url + '\n' + \
            'Error Detail: ' + detail + '\n' + \
            'Check with Feed Validator: ' + \
            'http://www.feedvalidator.org/check?url=' + validate + '\n'
   payload = payload.encode('iso-8859-1')
   msg.set_payload(payload, 'iso-8859-1')

   output = msg.as_string(True)
   output += '\n\n' # mbox seperator
   del msg

   writeMailbox(mbox, output)

   return

def rssToMbox(data):
   """
   args: data - feedparser data dictionary
   output: none
   returns: output string
   notes: this fcn is probably overkill since bloglines will normalize
         some of the RSS feed data
   """

   output = []

   title = data['feed']['title']
   if not title:
      title = '(untitled)'

   title = stripNewlines(string.strip(title))
   title = xml.sax.saxutils.unescape(title, ENTITY_DICT)

   clink = data['feed']['link']

   # need the following: feed - title, clink
   #                     item - date, ititle, guid, ilink, desc
   for article in data['entries']:

      if article.has_key('modified_parsed'):
         date = time.asctime(article['modified_parsed'])
      else:
         date = CURTIME

      desc = ""

      if article.has_key('content'):
         clist = article['content']

         # stop if we get html content, continue otherwise
         for datum in clist:
            if datum['type'] == "text/html":
               desc = datum['value']
               break
            elif datum['type'] == "application/xhtml+xml":
               desc = datum['value']
               break
            else: # probably "text/plain"
               desc = datum['value']

      if not len(desc):
         if article.has_key('description'):
            desc = article['description']

      if not len(desc):
         desc = '(none provided)'

      ititle = ""

      if article.has_key('title'):
         ititle = stripHtmlTags(article['title'])

      if not len(ititle):
         ititle = firstNwords(stripHtmlTags(desc)) + "..."

      ititle = xml.sax.saxutils.unescape(ititle, ENTITY_DICT)
      ititle = string.strip(ititle)

      if article.has_key('link'):
         ilink = article['link']
      elif article.has_key('guid'):
         ilink = string.strip(article['guid'])
      else:
         ilink = clink

      if article.has_key('guid'):
         guid = string.strip(article['guid'])
      else:
         if isinstance(desc, unicode):
            guidText = desc.encode('ascii', 'ignore')
         else:
            try:
               guidText = str(desc)
            except UnicodeError:
               desc = unicode(desc, 'ascii', 'replace').encode('ascii')
               guidText = desc

         ml = md5.new(guidText)
         guid = ml.hexdigest()
         del ml
      
      if article.has_key('enclosures'):
         enclosure = True
         fileURL = article['enclosures'][0]['url']
      else:
         enclosure = False

      msg = email.Message.Message()
      msg.set_unixfrom('From BLuMBOX@SynGen.rss ' + date)
      msg.add_header('From', '"' + title + '" <BLuMBOX@SynGen.rss>')
      msg.add_header('To', '"RSS eMail Reader" <MBOX@SynGen.rss>')
      msg.add_header('Subject', ititle)
      msg.add_header('X-RSS-Link', ilink)
      if enclosure:
         msg.add_header('X-RSS-Enclosure', fileURL)
      msg.add_header('Message-ID', '<' + guid + '@' + clink + '>')
      msg.add_header('Date', date)
      msg.set_type('text/html')
      msg.set_charset('utf-8')
      msg.epilogue = ''
      payload = u'<h4><a href="' + ilink + u'">'
      payload += ititle + u'</a></h4>\n<p>\n'
      payload += desc + u'\n</p>\n'
      if enclosure:
         payload += u'<p>[<a href="' + fileURL + u'">Enclosure</a>]</p>'
      payload = payload.encode('utf-8')
      msg.set_payload(payload, 'utf-8')

      output.append(msg.as_string(True))
      output.append('\n\n') # mbox seperator
      del msg

   return string.join(output, "")

def processFeed(url, mbox):
   """
   args: url - RSS url 
         mbox - name of mailbox
   output: none
   returns: none / raise exception
   """

   data = getBLdata(url)
   newdata = feedparser.parse(data)

   if len(newdata['items']):
      output = rssToMbox(newdata)

      if len(output) > 0:
         writeMailbox(mbox, output)
      
   elif newdata.has_key('status'):
      status = newdata['status']
      if status > 399:
         detail = "received HTTP error " + str(status)
         reportFeedError(detail, url, mbox)
   else:
      pass # let it go, could be xml error or not modified

   return

def getFeedInfo():
   """
   args: none
   output: none
   returns: data from feed file in raw format
   """

   fp = file(FEEDFILE, 'r')
   data = fp.read()
   fp.close()
   return data

def checkFeeds():
   """
   args: none
   output: error text on Fail
   returns: 0 - Success, > 0 - Fail
   """

   rc = 0

   try:
      # feeds[key] = val, key = bloglinesSubId, val = mbox name
      feeds = getBLfeeds(BLOPMLURL)
   except:
      print "Unable to get BlogLines OPML subscriptions", BLOPMLURL
      rc = 1
   else:
      for subid in feeds.keys():
         mail = feeds[subid]
         mbox = MAILDIR + "/" + mail

         try:
            processFeed(subid, mbox)
         except Exception, detail:
            detail = formatExceptionInfo()
            reportFeedError(detail, subid, mbox)

   return rc

# ----------------------------------------------------------------------

def main():
   """
   args: uses sys.argv if exists
   output: useful status/error messages; hopefully
   returns: 0 - success, 1 - fail - uses sys.exit()
   """

   if len(sys.argv) > 1:
      if sys.argv[1] == "-debug":
         _DEBUG = 1

   if checkFeeds():
      print "Error processing feeds, aborting"
      sys.exit(1)

   sys.exit(0)

if __name__ == '__main__':
   main()
