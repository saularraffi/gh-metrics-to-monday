from datetime import datetime
import requests
import argparse
import json
import ast
import re
import os

parser = argparse.ArgumentParser()

parser.add_argument('-gt', '--github-token', required=True, help='GitHub token used to call GitHub API')
parser.add_argument('-pr', '--pr-number', required=True, help='PR number being evaluated for churn')
parser.add_argument('-b', '--branch', default='main', help='Destination branch name (the branch being merged to)')
parser.add_argument('-o', '--owner', required=True, help='Owner of the pull request')
parser.add_argument('-r', '--repo', required=True, help='Name of the repository')

args = parser.parse_args()

GH_TOKEN        = command_output = os.popen('gh auth token').read().strip()
REQUEST_HEADERS = { 'Authorization': f'Bearer { GH_TOKEN }' }
GH_GRAPHQL_URL  = 'https://api.github.com/graphql'
PR_NUMBER       = args.pr_number
BRANCH          = args.branch
OWNER           = args.owner
REPO            = args.repo

def getFileCommitHistoryQuery(filename):
    global OWNER
    global REPO
    global BRANCH

    return '''
        query {
            repository(owner: \"%s\", name: \"%s\") {
                object(expression: \"%s\") {
                    ... on Commit {
                        blame(path: \"%s\") {
                            ranges {
                                commit {
                                    committedDate
                                }
                                startingLine
                                endingLine
                            }
                        }
                    }
                }
            }
        }
    ''' % (OWNER, REPO, BRANCH, filename)

def fetchFileCommitHistory(query):
    response = requests.post(
        GH_GRAPHQL_URL,
        headers=REQUEST_HEADERS,
        json={'query': query}
    )

    commits = response.json()['data']['repository']['object']['blame']['ranges']

    commitHistory = []

    for commit in commits:
        date = commit['commit']['committedDate']
        startL = commit['startingLine']
        endL = commit['endingLine']
        commitHistory.append(f"({startL},{endL}) {date}")
    
    return commitHistory

def fetchPrDiffFiles(prNumber):
    url = f'https://api.github.com/repos/{OWNER}/{REPO}/pulls/{prNumber}/files'
    headers = {
        'Authorization': REQUEST_HEADERS['Authorization'],
        'Accept': 'application/vnd.github.v3+json'
    }

    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        return { 'error': f'{response.status_code} - {response.text}' }
    
    return { 'data': response.json() }

def fetchRepoContributors():
    url = f'https://api.github.com/repos/{OWNER}/{REPO}/contributors'
    headers = {
        'Authorization': REQUEST_HEADERS['Authorization'],
        'Accept': 'application/vnd.github.v3+json'
    }

    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        return { 'error': f'{response.status_code} - {response.text}' }
    
    contributors = []

    for contributor in response.json():
        contributors.append(contributor['login'])

    print(contributors)
        
    return contributors
    
def splitHunks(patch):
    pattern = r"(@@ [^@]+ @@)"
    splitResult = re.split(pattern, patch)

    result = []
    for i in range(1, len(splitResult), 2):
        result.append(splitResult[i] + splitResult[i + 1])
    
    return result

def getValuesFromHunkHeader(hunkHeader):
    hunkParts = hunkHeader.split()
    originalInfo = hunkParts[1][1:]
    newInfo = hunkParts[2][1:]

    originalStart, originalCount = map(int, originalInfo.split(','))
    newStart, newCount = map(int, newInfo.split(','))

    return { 
        '-start': originalStart,
        '-count': originalCount,
        '+start': newStart,
        '+count': newCount 
    }

def getLinesChangedInPatch(patch):
    hunks = splitHunks(patch)

    linesChanged = []

    for hunk in hunks:
        lines = hunk.split('\n')
        hunkValues = getValuesFromHunkHeader(lines[0])

        changeEncountered = False
        start = offset = hunkValues['-start']
        lastChangedLine = 0
        linesToRollback = 0

        for n, line in enumerate(lines[1:]):
            lineNumber = offset + n

            if line.startswith('+') and not changeEncountered:
                linesToRollback += 1

            if line.startswith('-') and not changeEncountered:
                start = lineNumber - linesToRollback

            if line.startswith('-'):
                changeEncountered = True
            
            if not line.startswith('-') and changeEncountered:
                linesChanged.append((start, lineNumber - 1 - linesToRollback))
                changeEncountered = False
                linesToRollback = 0

    return linesChanged

def getLinesChangedInPr(prNumber):
    prData = fetchPrDiffFiles(prNumber)

    if 'error' in prData.keys():
        return {}
    
    diffTable = {}

    for file in prData['data']:
        patch = file.get("patch", "")
        linesChanged = getLinesChangedInPatch(patch)
        diffTable[file['filename']] = linesChanged
    
    return diffTable

def getDaysOld(dateStr):
    now = datetime.now().date()
    dateTimeObj = datetime.fromisoformat(dateStr.replace('Z', ''))
    date = dateTimeObj.date()
    return (now - date).days

def getChangeHistoryForAllContributors(filename):
    contributors = fetchRepoContributors()

    totalCommitHistory = []

    for contributor in contributors:
        query = getFileCommitHistoryQuery(filename)
        commitHistory = fetchFileCommitHistory(query)
        totalCommitHistory += commitHistory

    return totalCommitHistory

def getLinesChangedInDestination(files, linesWithinNDays=90):
    destinationBranchChangeTable = {}

    for filename in files:
        commitHistory = getChangeHistoryForAllContributors(filename)

        destinationBranchChangeTable[filename] = []
        
        for commit in commitHistory:
            changeStr, dateStr = commit.split(' ')
            change = ast.literal_eval(changeStr)
            daysOld = getDaysOld(dateStr)

            if daysOld <= linesWithinNDays:
                destinationBranchChangeTable[filename].append(change)
        
        if len(destinationBranchChangeTable[filename]) == 0:
            del destinationBranchChangeTable[filename]
        else:
            destinationBranchChangeTable[filename] = sorted(
                destinationBranchChangeTable[filename],
                key=lambda x: x[0]
            )
    
    return destinationBranchChangeTable

def getOverlappingLinesChanged(changeSet1, changeSet2):
    list1 = changeSet1
    list2 = changeSet2

    ptr1 = 0
    ptr2 = 0

    overlapping = []

    while ptr1 < len(list1) and ptr2 < len(list2):
        #     ---
        # ---
        if list1[ptr1][0] > list2[ptr2][1]:
            ptr2 += 1
        # ---
        #     ---
        elif list1[ptr1][1] < list2[ptr2][0]:
            ptr1 += 1
        
        elif list1[ptr1][0] >= list2[ptr2][0]:
            # ---
            #     ---
            if list1[ptr1][1] >= list2[ptr2][1]:
                overlapping.append((list1[ptr1][0], list2[ptr2][1]))
                ptr2 += 1
            #  ---
            # -----
            else:
                overlapping.append((list1[ptr1][0], list1[ptr1][1]))
                ptr1 += 1
        elif list1[ptr1][0] <= list2[ptr2][0]:
            # ---
            #  ---
            if list1[ptr1][1] <= list2[ptr2][1]:
                overlapping.append((list2[ptr2][0], list1[ptr1][1]))
                ptr1 += 1
            # -----
            #  ---
            else:
                overlapping.append((list2[ptr2][0], list2[ptr2][1]))
                ptr2 += 1
    
    return overlapping

def getTotalLinesChanged(changedLines):
    total = 0

    for changeRange in changedLines:
        _sum = changeRange[1] - changeRange[0] + 1
        total += _sum
    
    return total

def main():
    prChangeData = getLinesChangedInPr(PR_NUMBER)

    filenames = [filename for filename in prChangeData]
    destinationChangeData = getLinesChangedInDestination(filenames)

    totalLinesChanged = 0

    for filename, changes in destinationChangeData.items():
        linesChangedInFile = 0

        if filename in prChangeData.keys():
            changeSet1 = prChangeData[filename]
            changeSet2 = changes

            overlap = getOverlappingLinesChanged(changeSet1, changeSet2)
            
            linesChangedInFile = getTotalLinesChanged(overlap)
            totalLinesChanged += linesChangedInFile

    # print(totalLinesChanged)

if __name__ == '__main__':
    main()