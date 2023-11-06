import argparse
from DART import *
from pprint import pprint

# ----------------------------------------------------- 

parser = argparse.ArgumentParser(description='Esegui il test web of trust con partecipazione attiva (test scenario B paper ICDCS).')
parser.add_argument('--build', type=str,
                        default='build/contracts/DART.json',
                        help="path all'artifact DART.json prodotto da Truffle a seguito della compilazione (default: build/contracts/DART.json)")
parser.add_argument('--host', type=str,
                        default='http://localhost:8545',
                        help="hostname e porta della blockchain su cui è stato deployato DART (default: http://localhost:8545)")
parser.add_argument('--netid', type=int,
                        default=1,
                        help="network id della blockchain (default: 1)")
parser.add_argument(dest='n_partecipants', type=int, help='numero di principals partecipanti alla web of trust (almeno 2)')
args = parser.parse_args()

nPartecipants = args.n_partecipants

if nPartecipants < 2:
    print("At least 2 partecipants are needed in order to run this test")

# Inizializza web3 connettendolo al provider locale ganache
w3 = Web3(Web3.HTTPProvider(args.host))
accounts = w3.eth.accounts;
w3.eth.defaultAccount = accounts[0]

if len(accounts) < nPartecipants:
    print("Not enough available Ethereum accounts! At least N_partecipants accounts are needed in order to run this test")
    sys.exit(-1)

accounts = accounts[:nPartecipants]

# Inizializza l'interfaccia per interagire con lo smart contract DART
DARTArtifact = json.load(open(args.build))
d = DART(DARTArtifact['abi'], DARTArtifact['networks'][str(args.netid)]['address'], w3)

# ----------------------------------------------------- 

# Per facilitare la stesura dei test e la lettura dei risultati
# realizza due coppie di dizionari per legare:

# ... principals ad address e viceversa
PR = {}
for idx, addr in enumerate(accounts):
    PR['Principal[' + str(idx+1) + ']'] = addr
INV_PR = {v: k for k, v in PR.items()}
print("\nPRINCIPALS:")
pprint(PR)

# ... rolenames esadecimali a rolenames stringhe e viceversa
RN = {
    'trust': '0x200a',
}
INV_RN = {v: k for k, v in RN.items()}
print("\nROLENAMES:")
pprint(RN)


# Funzione di utilità per convertire una Expression in una stringa human-readable
def expr2str(expr):
    if isinstance(expr, SMExpression):
        return INV_PR[expr.member]
    elif isinstance(expr, SIExpression):
        return INV_PR[expr.principal] + "." + INV_RN[expr.roleName]
    elif isinstance(expr, LIExpression):
        return INV_PR[expr.principal] + "." + INV_RN[expr.roleNameA] + "." + INV_RN[expr.roleNameB]
    elif isinstance(expr, IIExpression):
        return INV_PR[expr.principalA] + "." + INV_RN[expr.roleNameA] + " ∩ " + INV_PR[expr.principalB] + "." + INV_RN[expr.roleNameB]


# -----------------------------------------------------

d.newRole(RN['trust'], {'from': accounts[0]})

for i in range(1, nPartecipants):

    print('\nAdding a new partecipant (active) to the web of trust... ', end='')

    d.newRole(RN['trust'], {'from': accounts[i]})
    d.addLinkedInclusion(RN['trust'], LIExpression(accounts[i], RN['trust'], RN['trust']), 80, {'from': accounts[i]})
    d.addSimpleMember(RN['trust'], SMExpression(accounts[i-1]), 100, {'from': accounts[i]})
    d.addSimpleMember(RN['trust'], SMExpression(accounts[i]), 100, {'from': accounts[i-1]})

    print(f'Number of total partecipants: {i+1}')

    # Effettua una ricerca locale di tutti i membri a cui risulta assegnato il ruolo Principal[i].trust
    print(f'\nExecuting off-line credential chain discovery on {INV_PR[accounts[i]]}.trust ... ', end='')
    solutions = d.search(SIExpression(accounts[i], RN['trust']))
    print(f"Found solutions: {len(solutions)}")

    # Per ciascun membro trovato, costruiscine la dimostrazione per il metodo di verifica on-chain sulla base dei paths nelle soluzioni
    for idx, currSol in enumerate(solutions.values()):
        print(f'\nSolution #{idx+1}: member={INV_PR[currSol.member]}, weight={currSol.weight}')
        proofStrs = []
        proof = []
        for currEdge in currSol.path:
            if not isinstance(currEdge.toNode.expr, LIExpression):
                proofStrs.append(expr2str(currEdge.toNode.expr) + ' ←- ' + expr2str(currEdge.fromNode.expr))
                proof.append(currEdge.toNode.expr.id)
                proof.append(currEdge.fromNode.expr.id)

        # Verifica la dimostrazione on-chain
        print('Constructed verification proof:')
        pprint(proofStrs)
        print(f'Required stack size: {currSol.reqStackSize}')
        verifGas = d.contract.functions.verifyProof(proof, currSol.reqStackSize).estimateGas()
        verifRes = d.verifyProof(proof, currSol.reqStackSize)
        if verifRes['principal'] != accounts[i] or verifRes['rolename'] != RN['trust'] or verifRes['member'] != currSol.member or verifRes['weight'] != int(currSol.weight):
            print("ERROR: invalid proof for current solution!")
        else:
            verifRes['principal'] = INV_PR[verifRes['principal']]
            verifRes['rolename'] = INV_RN[verifRes['rolename']]
            verifRes['member'] = INV_PR[verifRes['member']]
        
        print(f'On-chain verification gas: {verifGas}')
        print(f'On-chain verification result: {verifRes}')
