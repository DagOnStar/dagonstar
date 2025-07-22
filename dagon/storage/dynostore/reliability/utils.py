import math
import numpy

def isPrime(p): 
    """
    Inputs:
    p : an integer
    Output: 
    True if p is prime, False otherwise
    """
    
    if p<2: 
        return False
    if p==2: 
        return True
    if p%2==0:
        return False
    for d in range(3,math.ceil(math.sqrt(p))+1): 
        if p%d==0: 
            return False
        
        else: 
            d+=2
    return True

def nextPrime(p): 
    '''
    Inputs: 
    p : an integer
    Output:
    next prime greater than p
    '''
    if p%2==0: 
        p+=1
    while not isPrime(p):
        p+=2
    return p

def inner_product(a, b, p): 
    """
    Inputs:
    a, b :  v ectors of equal length
    p: an integer, a prime number
    Output: 
    The inner product of a and b, where computations are done modulo p  
    """
    #print(sum((i*j) for i,j in zip(a,b)), p, sum((i*j) for i,j in zip(a,b))%p)
    return sum((i*j) for i,j in zip(a,b))%p
    
def matrix_product(A,B, p): 
    '''
    Inputs: 
    A, B : matrices of dimensions that are compatible for matrix multiplication
    p: an integer
    Output: 
    a matrix resulted from multiplication of A and B, where all computations are done modulo p
    '''
    
    result = []
    for i in range(len(A)):
        row=[]
        for j in range(len(B[0])): 
            ans=0
            for k in range(len(A[0])):
                ans=(ans+(A[i][k]*B[k][j]))%p
            row.append(ans)
        result.append(row)
    return result
    
def transpose(M): 
    result=[[0]*len(M) for _ in range(len(M))]
    for i in range(len(M)): 
        for j in range(len(M)): 
            result[i][j]=M[j][i]
    return result
    
def modulo_inverse(x,p): 
    """
    Inputs: 
    x : an integer
    p : an integer, a prime number
    Output:
    x^-1 mod p
    """
    
    t,new_t=0,1
    r,new_r=p, x
    while new_r: 
        quotient=r//new_r
        t,new_t = new_t, t-quotient*new_t
        r,new_r = new_r, r-quotient*new_r
    
    if r>1: 
        raise ValueError("{} is not invertible mod {}".format(x,p))
    if t<0:
        t=t+p
    return t
    
def build_building_blocks(m,n,p): 
    '''
    Inputs: 
    m, n, p: integers
    Output:
    return building_blocks where
    building_blocks[i]=(1, i, i**2, ..., i**(m-1)) for i in range(n) 
    all computations are done modulo p
    '''
    building_blocks=[]
    for a in range(1,n+1): 
        row = []
        elt = 1
        for i in range(m): 
            row.append(elt)
            elt=(elt*a)%p
        building_blocks.append(row)
    return building_blocks
    
def elementary_symmetric_functions(m,L,p): 
    """
    Inputs: 
    m : a integer
    L : a list of integers
    p : an integer, a prime number
    Output: 
    a list el where el[i] is the sum of prod of i distinct elements L
    where all computations are done modulo p
    el has length m+1
    """
    # Recusive relation: 
    # Let el[i][j] = the sum of prod of i distinct elments in L[:j]
    # then el[i][j]=el[i-1][j-1]*L[j]+el[i][j-1]
    el = [[0]*(len(L)+1) for _ in range(m+1)]
    for j in range(1,len(L)+1):
        el[1][j]=el[1][j-1]+L[j-1]
    
    for i in range(2,m+1): 
        for j in range(i,len(L)+1): 
            el[i][j]=el[i-1][j-1]*L[j-1]+el[i][j-1]
    
    return [el[i][-1] for i in range(0,m+1) ]

def vandermonde_inverse(vandermonde_basis,p): 
    '''
    Inputs: 
    vandermonde_basis : a list of integers that formed the vandermonde matrix
    p : an integer, a prime number
    Output: 
    the inverse matrix of the vandermonde matrix (forms by vandermonde_basis), 
    where all computations are done modulo p
    '''
    m = len(vandermonde_basis)
    
    # build a dictionary for modulo inverse
    inverses={}
    
    # build a list of elementary symmetric function
    # el[i] is the sum of prod of i disticnt elements in vandemonde_basis
    el = elementary_symmetric_functions(m, vandermonde_basis, p)
    
    # denominators of each row
    denominators=[]
    for i in range(m): 
        prod=1
        elt = vandermonde_basis[i]
        for j in range(m): 
            if j!=i: 
                prod=(prod*(elt-vandermonde_basis[j]))%p
        denominators.append(prod)
   
    # numerators for each row
    # perform synthetic division
    numerators=[]
    for i in range(m): 
        row=[1]
        elt = vandermonde_basis[i]
        sign=-1
        for j in range(1,m): 
            row.append(((row[-1]*elt)%p+sign*el[j])%p)
            sign*=-1
        row.reverse()
        numerators.append(row)
    
    result=[]
    for i in range(m): 
        denominator=denominators[i]
        if denominator in inverses: 
            inv=inverses[denominator]
        else: 
            inv=modulo_inverse(denominator,p)
            inverses[denominator]=inv
        
        row=list(map(lambda x: (x*inv)%p, numerators[i]))
        result.append(row)
    return transpose(result)
    
