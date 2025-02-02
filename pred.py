from ds import Dataset
from numpy.random import uniform
import numpy as np
from utils import err, Base, evaluate
from math import log, exp
from code import Coder
import json

class HMMPredictor(Base):
    def __init__(self, N, M, T, code, ds=None, atom='letter', supervised=True):
        self.save_hyperparameters()
        if self.ds:
            if self.supervised:
                self.cntA=np.zeros((self.N, self.N))
                self.cntB=np.zeros((self.N, self.M))
                self.cntpi=np.zeros(self.N)
            else:
                self.A=uniform(size=(self.N, self.N))
                self.B=uniform(size=(self.N, self.M))
                self.pi=uniform(size=self.N)
                self.A=np.array([(self.A[i]/sum(self.A[i]) if sum(self.A[i]) else self.A[i]) for i in range(self.N)])
                self.B=np.array([(self.B[i]/sum(self.B[i]) if sum(self.B[i]) else self.B[i]) for i in range(self.N)])
                self.pi=self.pi/sum(self.pi)
        else:
            try:
                if self.supervised:
                    with open(f'data/{atom}_cnt_dict.json','r') as f:
                        params=json.load(f)
                    self.cntA=np.array(params['cntA'])
                    self.cntB=np.array(params['cntB'])
                    self.cntpi=np.array(params['cntpi'])
                    self.A=np.array([(self.cntA[i]/sum(self.cntA[i]) if sum(self.cntA[i]) else self.cntA[i]) for i in range(self.N)])
                    self.B=np.array([(self.cntB[i]/sum(self.cntB[i]) if sum(self.cntB[i]) else self.cntB[i]) for i in range(self.N)])
                    self.pi=self.cntpi/sum(self.cntpi)
                else:
                    with open(f'data/{atom}_state_dict.json', 'r') as f:
                        params=json.load(f)
                    self.A=np.array(params['A'])
                    self.B=np.array(params['B'])
                    self.pi=np.array(params['pi'])
            except:
                raise RuntimeError(f'no {atom} state dict exists.')

    def get_alpha(self, O):
        alpha=[]
        alpha.append(np.array([self.pi[i]*self.B[i][O[0]] for i in range(self.N)]))
        for t in range(1,len(O)):
            alpha.append(np.array([self.B[i][O[t]]*sum([alpha[t-1][j]*self.A[j][i] for j in range(self.N)]) for i in range(self.N)]))
        return np.array(alpha)

    def get_beta(self, O):
        beta=[]
        beta.append(np.array([1 for i in range(self.N)]))
        for t in range(len(O)-2, -1, -1):
            beta.append(np.array([sum([self.A[i][j]*self.B[j][O[t+1]]*beta[-1][j] for j in range(self.N)]) for i in range(self.N)]))
        return np.array(beta[::-1])

    def get_gamma(self, alpha, beta, O):
        gamma=[]
        for t in range(len(O)):
            s=sum([alpha[t][i]*beta[t][i] for i in range(self.N)])
            gamma.append(np.array([alpha[t][i]*beta[t][i]/s for i in range(self.N)]))
        return np.array(gamma)

    def get_xi(self, alpha, beta, O):
        xi=[]
        for t in range(len(O)-1):
            s=sum([alpha[t][i]*self.A[i][j]*self.B[j][O[t+1]]*beta[t+1][j] for i in range(self.N) for j in range(self.N)])
            xi.append(np.array([np.array([(alpha[t][i]*self.A[i][j]*self.B[j][O[t+1]]*beta[t+1][j]/s if s else 0)for j in range(self.N)]) for i in range(self.N)]))
        return np.array(xi)

    def step(self, datas):
        assert not(np.isnan(self.A).any() or np.isnan(self.B).any() or np.isnan(self.pi).any()), 'Nan in A, B, pi'
        assert len(self.A.nonzero()), 'A are all zeros'
        assert len(self.B.nonzero()), 'B are all zeros'
        assert len(self.pi.nonzero()), 'pi are all zeros'
        gamma=[]
        xi=[]
        for sentence in datas:
            alpha=self.get_alpha(sentence)
            beta=self.get_beta(sentence)
            gamma.append(self.get_gamma(alpha, beta, sentence))
            xi.append(self.get_xi(alpha, beta, sentence))
        # print('Pre-calculation complete.')
        A, B=[], []
        for i in range(self.N):
            nowA=[]
            s1=sum([gamma[epoch][t][i] for epoch in range(len(datas)) for t in range(len(datas[epoch]))])
            for j in range(self.N):
                s2=sum([xi[epoch][t][i][j] for epoch in range(len(datas)) for t in range(len(datas[epoch])-1)])
                nowA.append(s2/s1 if s1 else 0)
            A.append(np.array(nowA))
        # print('A calculation done.')
        for j in range(self.N):
            nowB=[]
            s1=sum([gamma[epoch][t][j] for epoch in range(len(datas)) for t in range(len(datas[epoch]))])
            for k in range(self.M):
                s2=sum([gamma[epoch][t][j]*(datas[epoch][t]==k) for epoch in range(len(datas)) for t in range(len(datas[epoch]))])
                nowB.append(s2/s1 if s1 else 0)
            B.append(np.array(nowB))
        # print('B calculation done.')
        pi=[sum([gamma[epoch][t][i] for epoch in range(len(datas)) for t in range(len(datas[epoch])) if self.code.is_begin(datas[epoch][t])]) for i in range(self.N)]
        # print('pi calculation done.')

        A, B, pi=np.array(A), np.array(B), np.array(pi)
        loss=abs(self.A-A).sum()+abs(self.B-B).sum()+abs(self.pi-pi).sum()
        self.A, self.B, self.pi=A, B, pi
        return loss

    def train(self, loop_lim): 
        assert self.ds, 'You should have your dataset before training.'
        datas=self.ds.get_train_data()
        sentences=[self.code.encode_sentence(data, train=self.supervised, atom=self.atom) for data in datas]
        if self.supervised:
            for sentence in sentences:
                for i in range(len(sentence)):
                    if self.atom=='letter':
                        self.cntpi[sentence[i]['tag']]+=self.code.is_begin(sentence[i]['tag'])
                    else:
                        self.cntpi[sentence[i]['tag']]+=(i==0)
                    if i<len(sentence)-1:
                        self.cntA[sentence[i]['tag']][sentence[i+1]['tag']]+=1
                    self.cntB[sentence[i]['tag']][sentence[i]['ID']]+=1
            self.A=np.array([(self.cntA[i]/sum(self.cntA[i]) if sum(self.cntA[i]) else self.cntA[i]) for i in range(self.N)])
            self.B=np.array([(self.cntB[i]/sum(self.cntB[i]) if sum(self.cntB[i]) else self.cntB[i]) for i in range(self.N)])
            self.pi=self.cntpi/sum(self.cntpi)
        else:
            for i in range(loop_lim):
                loss=self.step(sentences)
                print(f'Update {i} time: loss {loss}')
                if loss<err:
                    break
    
    def predict(self, line):
        assert self.A is not None and self.B is not None and self.pi is not None, 'model need to be trained'
        O=self.code.encode_sentence(line, train=False, atom=self.atom)
        logp=[np.array([-np.log(self.pi[i])-np.log(self.B[i][O[0]]) for i in range(self.N)])]
        frm=[np.array([])]
        for t in range(1, len(O)):
            b=self.B[:,O[t]]
            nowlogp=(np.expand_dims(logp[t-1], axis=0)-np.log(self.A.T)-np.expand_dims(np.log(b),axis=1))
            logp.append(nowlogp.min(axis=1))
            frm.append(nowlogp.argmin(axis=1))
        
        endstate=self.code.get_all_ends()[logp[-1][self.code.get_all_ends()].argmin()] if self.atom=='letter' else logp[-1].argmin()
        I=[endstate]
        for t in range(len(O)-1,0,-1):
            endstate=frm[t][endstate]
            I.append(endstate)
        I=I[::-1]
        sentence=[{'ID': ID, 'tag': tag} for ID, tag in zip(O,I)]
        return self.code.decode_sentence(sentence, atom=self.atom)

    def save(self):
        assert self.ds is not None, 'need to train before saving'
        if self.supervised:
            with open(f'data/{self.atom}_cnt_dict.json','w') as f:
                json.dump({'cntA': self.cntA.tolist(), 'cntB': self.cntB.tolist(), 'cntpi': self.cntpi.tolist()}, f, indent='\t')
        else:
            with open(f'data/{self.atom}_state_dict.json','w') as f:
                json.dump({'A': self.A.tolist(), 'B': self.B.tolist(), 'pi': self.pi.tolist()}, f, indent='\t')