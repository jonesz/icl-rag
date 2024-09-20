from io import StringIO
import re
import glob
from datetime import date
import nltk.data
import time

from pdfminer.converter import TextConverter
from pdfminer.layout import LAParams
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser
from pdfminer.high_level import extract_text

tokenizer = nltk.data.load('tokenizers/punkt/english.pickle') # load the tokenizer model

def getLastOfIterator(iterator):
    item = None
    for item in iterator:
        pass
    return item

def getLines(fileName):
    output_string = StringIO()
    with open(fileName, 'rb') as in_file:
        parser = PDFParser(in_file)
        doc = PDFDocument(parser)
        rsrcmgr = PDFResourceManager()
        device = TextConverter(rsrcmgr, output_string, laparams=LAParams())
        interpreter = PDFPageInterpreter(rsrcmgr, device)
        numPages = 0
        for pageNumber, page in enumerate(PDFPage.create_pages(doc)):
            numPages = numPages + 1
            try:
                interpreter.process_page(page)
            except:
                print("Page " + str(pageNumber) + " in " + fileName + " could not be processed")
    return (output_string.getvalue().split("\n"), numPages)

def isCaption(line):
    return re.search(r'^((Figure)|(Table))', line) # Search for 'Figure' and 'Table'

def isNumberOrHeading(line):
    return re.search(r'^(\d||[Cc]hapter)',line) # Search for leading numbers, new page and 'Chapter'

def isShortText(line):
    return len(line) > 0 and len(line) < 60 and (not endsWithSentenceEndChar(line)) # Check if length less than 60 characters and text does not end with a sentence ending character 

def isTOCEntry(line):
    return re.search(r'\.\.\.\.+', line) # TOC entries always contain a lot of dots between chapter name and page

def filterLine(line):
    global numFilteredChars
    if isCaption(line):
        #print("Caption: " + line)
        numFilteredChars = numFilteredChars + len(line)
        return False
    if isNumberOrHeading(line):
        #print("Number or heading: " + line)
        numFilteredChars = numFilteredChars + len(line)
        return False
    if isShortText(line):
        #print("short text: " + line)
        numFilteredChars = numFilteredChars + len(line)
        return False
    if isReference(line):
        #print("reference: " + line)
        numFilteredChars = numFilteredChars + len(line)
        return False
    if isTOCEntry(line):
        numFilteredChars = numFilteredChars + len(line)
        return False
    return True

def startsWithCap(sentence):
    return re.search(r'^[A-Z]', sentence)

def endsWithSentenceEndChar(sentence):
    return re.search(r'(\.|\?|\!)$', sentence)

def filterSentence(sentence):
    global numFilteredChars
    if (len(sentence) > 50 # Sentences must be longer than 50 characters
            and startsWithCap(sentence) # Sentences have to start with a capital letter
            and endsWithSentenceEndChar(sentence)): # Sentences have to end with a sentence ending character
        numFilteredChars = numFilteredChars + len(sentence)
        return True
    return False

def isReference(line):
    return re.search(r'^(\[\d*\])\s*',line) # Search for reference brackets and 'o'

def preprocessSentence(sentence):
    global numFilteredChars
    lenBefore = len(sentence)
    sentence = re.sub(r'[Nn][Oo][Tt][Ee](?!\,?\sthat)\:?\s?\d*\s*', "", sentence) # remove prefixes that indicate a note, but keep 'Note that...'
    numFilteredChars = numFilteredChars + (lenBefore - len(sentence))
    return sentence

def preprocessLine(line):
    global numFilteredChars
    lenBefore = len(line)
    line = line.lstrip().rstrip() # remove all leading and trailing whitespaces 
    line = re.sub(r'^.\.\s*', "", line) # remove prefixes like 'A. blablabla', 'B. second blabla'
    line = re.sub(r'^\(?.\)\s*', "", line) # remove prefixes like 'a) bla', 'b) blabla' or '(a)', '(b)'
    line = re.sub(r'(•|||−|(\(cid\:1\)))\s*', "", line) # remove enumertion prefixes
    line = re.sub("\s+", " ", line) # we compress multiple whitespaces to one
    numFilteredChars = numFilteredChars + (lenBefore - len(line))
    return line

def getParagraphs(lines):
    paragraphs = []
    currentParagraph = []
    for line in lines:
        if len(line) == 0: # we start a new paragraph at every empty line
            if len(currentParagraph) > 0: # we dont want to add empty paragraphs
                paragraphs.append(" ".join(currentParagraph)) # combine all lines in current paragraph
            currentParagraph = []
        else:
            currentParagraph.append(line)
    return paragraphs

def splitAt(text, splitter):
    parts = text.split(splitter)
    finalParts = [parts[0]]
    for (n, part) in enumerate(parts, start=0):
        if n > 0:
            finalParts.append(splitter + part)
    return finalParts

def getSentencesForParagraph(paragraph):
    tokenizedSentences = tokenizer.tokenize(paragraph) # use the nltk tokenizer as first step
    sentences = []
    currSentence = None
    concatenate = False
    for sentence in tokenizedSentences:
        if concatenate: # last sentence ended with e.g. or i.e. -> we have to concatenate this one
            currSentence = currSentence + " " + sentence
        else:
            if currSentence != None:
                sentences = sentences + splitAt(currSentence, "The") # Manually split sentences at 'The' as this definitely marks a sentence start
            currSentence = sentence
        concatenate = re.search(r'([Ee]\.[Gg]\.|[Ii]\.[Ee]\.)$', sentence) # Concatenate next sentence if this one ends with 'e.g.' or 'i.e.' -> tokenizer is bad here
    sentences = sentences + splitAt(currSentence, "The") # Manually split sentences at 'The' as this definitely marks a sentence start
    return sentences

def writeStrings(strings, fileName, extension):
    outputFileName = fileName.split(".pdf")[0] + extension
    output = open(outputFileName, "w", encoding='utf-8')
    for string in strings:
        output.write(string + "\n")
    output.close()

def extractSentencesForFile(fileName):
    (lines, numPages) = getLines(fileName)
    lines = list(map(preprocessLine, lines)) # preprocess lines
    lines = list(filter(filterLine, lines)) # filter lines
    paragraphs = getParagraphs(lines)
    sentences = []
    for paragraph in paragraphs:
        parSentences = getSentencesForParagraph(paragraph)
        parSentences = list(filter(filterLine, parSentences)) # filter sentences with line filtering
        sentences = sentences + parSentences
    sentences = list(map(preprocessSentence, sentences)) # preprocess sentences
    sentences = list(filter(filterSentence, sentences)) # filter sentences with specific filters
    return (sentences, numPages)

def appendSentences(sentences, fileName):
    with open(fileName, "a+", encoding="utf-8") as file:
        for sentence in sentences:
            file.write(sentence + "\n")


reqFileNames = glob.glob("*.pdf") # get all pdf files
now = int(round(time.time() * 1000))
outputFileName = "sentences_" + str(now) + ".txt"
totalSize = 0
maxNumPages = 0
minNumPages = 10000000
averageNumPages = 0
numFilteredChars = 0
for fileName in reqFileNames:
    print(fileName)
    deletedCharsBefore = numFilteredChars
    (newSentences, numPages) = extractSentencesForFile(fileName) # process file
    maxNumPages = max(maxNumPages, numPages)
    minNumPages = min(minNumPages, numPages)
    averageNumPages = averageNumPages + numPages
    totalSize = totalSize + len(newSentences)
    appendSentences(newSentences, outputFileName)
    print("Added " + str(len(newSentences)) + " requirements for document " + fileName)
    print("Pages: " + str(numPages))
    print("Characters filtered: " + str(numFilteredChars - deletedCharsBefore))

print("-> Total requirements: " + str(totalSize))
print("-> max num pages: " + str(maxNumPages))
print("-> min num pages: " + str(minNumPages))
# print("-> average num pages: " + str((averageNumPages / len(reqFileNames))))
print("-> total filtered characters: " + str(numFilteredChars))
