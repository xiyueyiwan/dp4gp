# Methods for combining differential privacy with Gaussian Processes

import GPy
from sklearn.metrics import mean_squared_error
import numpy as np
import sys
import scipy
from scipy.stats import multivariate_normal
from scipy.optimize import minimize
import matplotlib.pyplot as plt
from dp4gp.utils import compute_Xtest, dp_unnormalise

class DPGP(object):
    """(epsilon,delta)-Differentially Private Gaussian Process predictions"""
    
    def __init__(self,model,sens,epsilon,delta):
        """
        Parameters:
            model = Pass a GPy model object
            sens = data sensitivity (how much can one output value vary due to one person
            epsilon = epsilon (DP parameter)
            delta = delta (DP parameter) [probability of providing DP]
            
        """
        self.model = model
        self.sens = sens
        self.epsilon = epsilon
        self.delta = delta
    
    def draw_prediction_samples(self,Xtest,N=1,Nattempts=7,Nits=1000,verbose=False):
        GPymean, covar = self.model.predict_noiseless(Xtest)
        mean, noise, cov = self.draw_noise_samples(Xtest,N,Nattempts,Nits,verbose=verbose)
        #TODO: In the long run, remove DP4GP's prediction code and just use GPy's
        #print GPymean-mean
        #assert np.max(GPymean-mean)<1e-2, "DP4GP code's posterior mean prediction differs from GPy's by %0.5f" % (np.max(GPymean-mean))
        return mean + noise.T, mean, cov
    

    def plot(self,fixed_inputs=[],legend=False,plot_data=False, steps=None, N=10, Nattempts=1, Nits=500, extent_lower={}, extent_upper={},norm_params=None,plotGPvar=True,confidencescale=[1.0],verbose=False,resolution=300,plot_colorbar=False):
        """
        Plot the DP predictions, etc.
        
        In 2d it shows one DP sample, the size of the circles represent the prediction values
        the alpha how much DP noise has been added (1->no noise, 0->20% of max-min prediction
        
        fixed_inputs = list of pairs
        legend = whether to plot the legend
        plot_data = whether to plot data
        steps = resolution of each plot axis (defaults to 100 in 1d, 10x10=100 in 2d, 4x4x4=64 in 3d, 3^4=81 in 4d,...)
        N = number of DP samples to plot (in 1d)
        Nattempts = number of times a DP solution will be looked for (can help avoid local minima)
        Nits = number of iterations when finding DP solution
        (these last two parameters are passed to the draw_prediction_samples method).
        confidencescale = how wide the CI should be (default = 1 std.dev)
        norm_params = dictionary containing mean and std from dp_normalisation
        resolution = resolution of GPy plot
        """
        
        if norm_params is None:
            norm_params = {'mean':0.0,'std':1.0}        
        
        if steps is None:
            dims = self.model.X.shape[1]-len(fixed_inputs) #get number of dims
            steps = int(100.0**(1.0/dims)) #1d=>100 steps, 2d=>10 steps
        Xtest, free_inputs, _ = compute_Xtest(self.model.X, fixed_inputs, extent_lower=extent_lower, extent_upper=extent_upper, steps=steps)

        preds, mu, cov = self.draw_prediction_samples(Xtest,N,Nattempts=1,Nits=Nits,verbose=verbose)
        preds = dp_unnormalise(preds,norm_params)
        mu = dp_unnormalise(mu,norm_params)
        cov *= (norm_params['std']**2)

        assert len(free_inputs)<=2, "You can't have more than two free inputs in a plot"
        if len(free_inputs)==1:
            pltlim = [np.min(Xtest[:,free_inputs[0]]),np.max(Xtest[:,free_inputs[0]])]
        if len(free_inputs)==2:
            pltlim = [[np.min(Xtest[:,free_inputs[0]]),np.min(Xtest[:,free_inputs[1]])],[np.max(Xtest[:,free_inputs[0]]),np.max(Xtest[:,free_inputs[1]])]] 

        #print(free_inputs[0])
        #print(Xtest[:,free_inputs[0]])
        #print(pltlim)
        DPnoise = np.sqrt(np.diag(cov))
        indx = 0
        if len(free_inputs)==2:
            #print(plot_data)
            self.model.plot(plot_limits=pltlim,fixed_inputs=fixed_inputs,legend=legend,plot_data=plot_data,resolution=resolution,plot_inducing=False)#plot_raw=True,
            if plot_colorbar:
                ax = plt.gca()
                mappable = ax.collections[0]
                mappable
                plt.colorbar(mappable)
            minpred = np.min(mu)
            maxpred = np.max(mu)
            scaledpreds = (70+600*(preds[:,indx]-minpred) / (maxpred-minpred)) / np.sqrt(steps)
            scalednoise = 1-2.5*DPnoise/(maxpred-minpred) #proportion of data
            
            #any shade implies the noise is less than 40%(?) of the total change in the signal
            scalednoise[scalednoise<0] = 0
            rgba = np.zeros([len(scalednoise),4])
            rgba[:,0] = 1.0
            rgba[:,3] = scalednoise
            plt.scatter(Xtest[:,free_inputs[0]],Xtest[:,free_inputs[1]],scaledpreds,color=rgba)
            
            if plot_data:
                plt.plot(self.model.X[:,free_inputs[0]],self.model.X[:,free_inputs[1]],'.k',alpha=0.2)

            plt.xlim(pltlim[0][0],pltlim[1][0])
            plt.ylim(pltlim[0][1],pltlim[1][1])
            
            if type(self.model)==GPy.models.sparse_gp_regression.SparseGPRegression:
                #draw the inducing points
                plt.plot(self.model.Z.values[:,0],self.model.Z.values[:,1],'+k',mew=2,markersize=8)


        if len(free_inputs)==1:
            gpmus, gpcovs = self.model.predict_noiseless(Xtest)
            gpmus = dp_unnormalise(gpmus,norm_params)
            gpcovs *= norm_params['std']**2
            
            plt.plot(Xtest[:,free_inputs[0]],gpmus)
            ax = plt.gca()           
            if plotGPvar: 
                ax.fill_between(Xtest[:,free_inputs[0]], (gpmus-np.sqrt(gpcovs))[:,0], (gpmus+np.sqrt(gpcovs))[:,0],alpha=0.1,lw=0)
            plt.plot(Xtest[:,free_inputs[0]],preds,alpha=0.2,color='black')
            
            if not isinstance(confidencescale,list):
                confidencescale = [confidencescale]
                
            a = 1
            for i,cs in enumerate(confidencescale):
                plt.plot(Xtest[:,free_inputs[0]],mu[:,0]-DPnoise*cs,'--k',lw=2,alpha=a)
                plt.plot(Xtest[:,free_inputs[0]],mu[:,0]+DPnoise*cs,'--k',lw=2,alpha=a)            
                a = a * 0.5
               
            plt.xlim([np.min(Xtest[:,free_inputs[0]]),np.max(Xtest[:,free_inputs[0]])])
            
            bound = np.std(self.model.X,0)*0.35
            keep = np.ones(self.model.X.shape[0], dtype=bool)
            for finp in fixed_inputs:
               keep = (keep) & (self.model.X[:,finp[0]]>finp[1]-bound[finp[0]]) & (self.model.X[:,finp[0]]<finp[1]+bound[finp[0]])
            plt.plot(self.model.X[keep,free_inputs[0]],norm_params['mean']+self.model.Y[keep]*norm_params['std'],'k.',alpha=0.4)
            
            
            if type(self.model)==GPy.models.sparse_gp_regression.SparseGPRegression:
                #draw the inducing points
                ax = plt.gca()
                lower_ylim = ax.get_ylim()[0]
                print(lower_ylim)
                print(ax.get_ylim())
                plt.vlines(self.model.Z.values[:,0],lower_ylim,10+lower_ylim)
        return DPnoise      
            
        
        
class DPGP_prior(DPGP):
    """
    DP provided by adding a sample from the prior
    """
    
#    def __init__(self,model,sens,epsilon,delta):      
#        super(DPGP_prior, self).__init__(model,sens,epsilon,delta)
        
    def calc_msense(self,A):
        """
        originally returned the infinity norm*, but we've developed an improved value from
        this norm which only cares about values of the same sign (it is assumed that
        those of the opposite sign will work to reduce the sensitivity). We'll call
        this the matrix_sensitivity or msense
        * np.max(np.sum(np.abs(A),1))
        """
        v1 = np.max(np.abs(np.sum(A.copy().clip(min=0),1)))
        v2 = np.max(np.abs(np.sum((-A.copy()).clip(min=0),1)))
        return np.max([v1,v2])

    def draw_cov_noise_samples(self,test_cov,msense,N=1):        
        """
        Produce differentially private noise for this covariance matrix
        """
        G = np.random.multivariate_normal(np.zeros(len(test_cov)),test_cov,N)
        noise = G*self.sens*np.sqrt(2*np.log(2/self.delta))/self.epsilon
        noise = noise * msense
        #print(msense*self.sens*np.sqrt(2*np.log(2/self.delta))/self.epsilon)
        return np.array(noise), test_cov*(msense*self.sens*np.sqrt(2*np.log(2/self.delta))/self.epsilon)**2

    def draw_noise_samples(self,Xtest,N=1,Nattempts=7,Nits=1000,verbose=False):
        raise NotImplementedError #need to implemet in a subclass
        

class DPGP_normal_prior(DPGP_prior):
    def __init__(self,model,sens,epsilon,delta):      
        super(DPGP_normal_prior, self).__init__(model,sens,epsilon,delta)
        self.calc_invCov()
        
    def calc_invCov(self):
        """
        TODO
        """
        sigmasqr = self.model.Gaussian_noise.variance[0]
        K_NN_diags = self.model.kern.Kdiag(self.model.X)
        K_NN = self.model.kern.K(self.model.X)
        invCov = np.linalg.inv(K_NN+sigmasqr*np.eye(K_NN.shape[0]))
        self.invCov = invCov
        
    def draw_noise_samples(self,Xtest,N=1,Nattempts=7,Nits=1000,verbose=False):
        """
        For a given set of test points, find DP noise samples for each
        """
        test_cov = self.model.kern.K(Xtest,Xtest)
        msense = self.calc_msense(self.invCov)
        #print(msense)
        ##This code is only necessary for finding the mean (for testing it matches GPy's)
        sigmasqr = self.model.Gaussian_noise.variance[0]
        K_NN = self.model.kern.K(self.model.X)
        K_Nstar = self.model.kern.K(self.model.X,Xtest)
        mu = np.dot(np.dot(K_Nstar.T,np.linalg.inv(K_NN+sigmasqr*np.eye(K_NN.shape[0]))),self.model.Y)
        ##
        samps, samp_cov = self.draw_cov_noise_samples(test_cov,msense,N)
        return mu, samps, samp_cov
      
    
class DPGP_pseudo_prior(DPGP_prior):
    def draw_noise_samples(self,Xtest,N=1,Nattempts=7,Nits=1000,verbose=False):
        """
        For a given set of test points, find DP noise samples for each
        """
        self.model.inference_method = GPy.inference.latent_function_inference.FITC()
        test_cov = self.model.kern.K(Xtest,Xtest)
        sigmasqr = self.model.Gaussian_noise.variance[0]
        K_NN_diags = self.model.kern.Kdiag(self.model.X)
        K_NN = self.model.kern.K(self.model.X)
        
        K_star = self.model.kern.K(Xtest,self.model.Z.values)
        K_NM = self.model.kern.K(self.model.X,self.model.Z.values)
        K_MM = self.model.kern.K(self.model.Z.values)
        invK_MM = np.linalg.inv(K_MM)
        
        #lambda values are the diagonal of the training input covariances minus 
        #(cov of training+pseudo).(inv cov of pseudo).(transpose of cov of training+pseudo)
        lamb = np.zeros(len(self.model.X))
        for i,t_in in enumerate(self.model.X):
            lamb[i] = K_NN_diags[i] - np.dot(np.dot(K_NM[i,:].T,invK_MM),K_NM[i,:])

        #this finds (\Lambda + \sigma^2 I)^{-1}
        diag = 1.0/(lamb + sigmasqr) #diagonal values

        #rewritten to be considerably less memory intensive (and make it a little quicker)
        Q = K_MM + np.dot(K_NM.T * diag,K_NM)

        #find the mean at each test point
        pseudo_mu = np.dot(     np.dot(np.dot(K_star, np.linalg.inv(Q)),K_NM.T) *  diag  ,self.model.Y)

        #find the covariance
        #K_pseudoInv is the matrix in: mu = k_* K_pseudoInv y
        #i.e. it does the job of K^-1 for the inducing inputs case
        K_pseudoInv = np.dot(np.linalg.inv(Q),K_NM.T) * diag

        invlambplussigma = np.diag(1.0/(lamb + sigmasqr)) 
        assert (K_pseudoInv == np.dot(np.dot(np.linalg.inv(Q),K_NM.T),invlambplussigma)).all() #check our optimisation works

        #find the sensitivity for the pseudo (inducing) inputs
        pseudo_msense = self.calc_msense(K_pseudoInv)

        samps, samp_cov = self.draw_cov_noise_samples(test_cov,pseudo_msense,N)
        return pseudo_mu, samps, samp_cov    

class DPGP_cloaking(DPGP):
    """Using the cloaking method"""
    
    def __init__(self,model,sens,epsilon,delta):      
        super(DPGP_cloaking, self).__init__(model,sens,epsilon,delta)
        assert epsilon<=1, "The proof in Hall et al. 2013 is restricted to values of epsilon<=1."

    def calcM(self,ls,cs):
        """
        Find the covariance matrix, M, as the lambda weighted sum of c c^T
        """
        d = len(cs[0])
        M = np.zeros([d,d])
        ccTs = []
        for l,c in zip(ls,cs):        
            ccT = np.dot(c,c.T)
            #print c,ccT,l,M
            M = M + l*ccT       
            ccTs.append(ccT)
        return M

    def L(self,ls,cs):
        """
        Find L = -log |M| + sum(lambda_i * (1-c^T M^-1 c))
        """
        M = self.calcM(ls,cs)
        Minv = np.linalg.pinv(M)
        t = 0
        for l,c in zip(ls,cs):        
            t += l*(1-np.dot(np.dot(c.T,Minv),c))[0,0]

        return (np.log(np.linalg.det(Minv)) + t)
        #return t
        
    def dL_dl(self,ls,cs):
        """
        Find the gradient dL/dl_j
        """
        M = self.calcM(ls,cs)
        Minv = np.linalg.pinv(M)            
        grads = np.zeros(len(ls))    
        for j in range(len(cs)):        
            grads[j] = -np.trace(np.dot(Minv,np.dot(cs[j],cs[j].T)))     
        return np.array(grads)+1
    
    def findLambdas_grad(self, cs, maxit=700,verbose=False):
        """
        Gradient descent to find the lambda_is

        Parameters:
            cs = list of column vectors (these are the gradients of df*/df_i)

        Returns:
            ls = vector of lambdas

        """
        #ls = np.ones(len(cs))*0.7
        ls = 0.1*np.random.rand(len(cs))*0.8 #random numbers between 0.1 and 0.9
        lr = 0.05 #learning rate
        for it in range(maxit): 
            lsbefore = ls.copy()
            delta_ls = -self.dL_dl(ls,cs)*lr
            ls =  ls + delta_ls
            ls[ls<0] = 0
            #lr*=0.995
            if np.max(np.abs(lsbefore-ls))<1e-5:
                return ls
            if verbose: print(".",end='')
        if verbose: print("Stopped before convergence")
        return ls
    
    def findLambdas_scipy(self,cs, maxit=1000, verbose=False):
        """
        Find optimum value of lambdas, start optimiser with random lambdas.
        """
        #ls = np.ones(len(cs))*0.7
        ls = np.random.rand(len(cs))+0.5
        cons = ({'type':'ineq','fun':lambda ls:np.min(ls)})
        #cons = []
        #for i in range(len(ls)):
        #    cons.append({'type':'ineq', 'fun':lambda ls:ls[i]})
        res = minimize(self.L, ls, args=(cs), method='SLSQP', options={'ftol': 1e-12, 'disp': True, 'maxiter': maxit}, constraints=cons, jac=self.dL_dl)
        ls = res.x 
        #print ls
        return ls
    
    def findLambdas_repeat(self,cs,Nattempts=70,Nits=1000, verbose=False):
        """
        Call findLambdas repeatedly with different start lambdas, to avoid local minima
        """
        bestLogDetM = np.Inf
        bestls = None
        count = 0      
        while bestls is None: #TODO this keeps going potentially forever!
            for it in range(Nattempts):
                if verbose: print("*"),
                import sys
                sys.stdout.flush()
                
                ls = self.findLambdas_grad(cs,Nits,verbose=verbose)
                if np.min(ls)<-0.01:
                    continue
                M = self.calcM(ls,cs)
                detM = np.linalg.det(M)
                if detM<=0:
                    logDetM = -1000 #-np.inf #TODO How do we handle this?
                else:                    
                    logDetM = np.log(detM)
                if logDetM<bestLogDetM:
                    bestLogDetM = logDetM
                    bestls = ls.copy()
            count+=1
            if count>1000:
                raise ValueError('A value for the lambda vector cannot be computed given this cloaking matrix, cs. 1000 attempts have been made at convergence.')
        #if bestls is None:
        #    print("Failed to find solution")
        return bestls
    
    def calcDelta(self,ls,cs):
        """
        We want to find a \Delta that satisfies sup{D~D'} ||M^-.5(v_D-v_D')||_2 <= \Delta
        this is equivalent to finding the maximum of our c^T M^-1 c.
        """
        M = self.calcM(ls,cs)
        Minv = np.linalg.pinv(M)
        maxcMinvc = -np.Inf
        for l,c in zip(ls,cs):
            cMinvc = np.dot(np.dot(c.transpose(), Minv),c)
            if cMinvc>maxcMinvc:
                maxcMinvc = cMinvc
        return maxcMinvc

    def checkgrad(self,ls,cs):
        """
        Gradient check (test if the analytical derivative dL/dlambda_i almost equals the numerical one)"""
        approx_dL_dl = []
        d = 0.0001
        for i in range(len(ls)):
            delta = np.zeros_like(ls)
            delta[i]+=d
            approx_dL_dl.append(((self.L(ls+delta,cs)-self.L(ls-delta,cs))/(2*d)))
        approx_dL_dl = np.array(approx_dL_dl)

        print("Value:")
        print(self.L(ls,cs))
        print("Approx")
        print(approx_dL_dl)
        print("Analytical")
        print(self.dL_dl(ls,cs))
        print("Difference")
        print(approx_dL_dl-self.dL_dl(ls,cs))
        print("Ratio")
        print(approx_dL_dl/self.dL_dl(ls,cs))

    def get_C(self,Xtest):
        """
        Compute the value of the cloaking matrix (K_Nstar . K_NN^-1)
        """
        sigmasqr = self.model.Gaussian_noise.variance[0]
        K_NN = self.model.kern.K(self.model.X)
        K_NNinv = np.linalg.inv(K_NN+sigmasqr*np.eye(K_NN.shape[0]))
        K_Nstar = self.model.kern.K(Xtest,self.model.X)
        C = np.dot(K_Nstar,K_NNinv)
        return C
    
    def draw_noise_samples(self,Xtest,N=1,Nattempts=7,Nits=1000,verbose=False):
        """
        Provide N samples of the DP noise
        """
        #moved computation to seperate method so I can use C for other things
        C = self.get_C(Xtest)

        cs = []
        for i in range(C.shape[1]):
            cs.append(C[:,i][:,None])
        
        ls = self.findLambdas_repeat(cs,Nattempts,Nits,verbose=verbose)
        M = self.calcM(ls,cs)
        
        c = np.sqrt(2*np.log(2/self.delta))
        Delta = self.calcDelta(ls,cs)
        #in Hall13 the constant below is multiplied by the samples,
        #here we scale the covariance by the square of this constant.
        #if verbose: print(self.sens,c,Delta,self.epsilon,np.linalg.det(M))
        sampcov = ((self.sens*c*Delta/self.epsilon)**2)*M
        samps = np.random.multivariate_normal(np.zeros(len(sampcov)),sampcov,N)
        
        ###This code is only necessary for finding the mean
        mu = np.dot(C,self.model.Y)
        ###
        return mu, samps, sampcov
    
class Test_DPGP_cloaking(object):
    def test(self):
        sens = 2
        eps = 1.0
        delta = 0.01
        trainX = np.random.randn(50,1)*10 
        #trainX = np.arange(0,10,0.2)[:,None]
        trainy = np.sin(trainX)+np.random.randn(len(trainX),1)*0.5
        Xtest = np.arange(0,10,2)[:,None] #0.2

        mod = GPy.models.GPRegression(trainX,trainy)
        mod.Gaussian_noise = 0.5**2
        mod.rbf.lengthscale = 1.0
        dpgp = DPGP_cloaking(mod,sens,eps,delta)
        mean, noise, sampcov = dpgp.draw_noise_samples(Xtest,2)

        largest_notDP = -np.Inf
        #dpgp, noise, sampcov = get_noise(trainX,trainy,Xtest,sens,eps,delta)
        for perturb_index in range(50): 
            mod = GPy.models.GPRegression(trainX,trainy)
            mod.Gaussian_noise = 0.5**2
            mod.rbf.lengthscale = 1.0
            dpgp = DPGP_cloaking(mod,sens,eps,delta)
            muA, _ = dpgp.model.predict_noiseless(Xtest)
            pert_trainy = np.copy(trainy)
            pert_trainy[perturb_index]+=sens
            mod = GPy.models.GPRegression(trainX,pert_trainy)
            mod.Gaussian_noise = 0.5**2
            mod.rbf.lengthscale = 1.0
            dpgp = DPGP_cloaking(mod,sens,eps,delta)
            muB, _ = dpgp.model.predict_noiseless(Xtest)


            dist = multivariate_normal(muA[:,0],sampcov)
            dist_shift = multivariate_normal(muB[:,0],sampcov)
            N = 200000
            #print("These two numbers should be less than delta=%0.4f" % dpgp.delta)
            #print("Note epsilon = %0.4f" % dpgp.epsilon)
            pos = np.random.multivariate_normal(muA[:,0],sampcov,N)
            proportion_notDP_A = np.mean( (dist.pdf(pos)/dist_shift.pdf(pos))>np.exp(dpgp.epsilon) )
            pos = np.random.multivariate_normal(muB[:,0],sampcov,N)
            proportion_notDP_B = np.mean( (dist_shift.pdf(pos)/dist.pdf(pos))>np.exp(dpgp.epsilon) )
            assert proportion_notDP_A < dpgp.delta
            assert proportion_notDP_B < dpgp.delta

            largest_notDP = np.max([largest_notDP,proportion_notDP_A,proportion_notDP_B])
        print("The largest proportion of values exceeding the epsilon-DP constraint is %0.6f. This should be less than delta, which equals %0.6f" % (largest_notDP, dpgp.delta))
        
class DPGP_inducing_cloaking(DPGP_cloaking):
    """Using Cloaking and Inducing inputs
    
        model = GPy model, this needs to be a SparseGPRegression model, it will
        have its inference method set to FITC
        Z = inducing input locations. Currently uses whatever was set in the model.
        TO DO: If a number, then k-means clustering will
        be used to select the inducing inputs. Also can be a numpy array of
        locations. If unset, it will assume 10 inducing inputs.
        HOW DOES GPy SELECT THE DEFAULT LOCATIONS?
    """
    def __init__(self,model,sens,epsilon,delta,Z = None):
        super(DPGP_cloaking, self).__init__(model,sens,epsilon,delta)    
        self.model.inference_method = GPy.inference.latent_function_inference.FITC() #make GPy's match our own sparse method
        assert type(self.model)==GPy.models.sparse_gp_regression.SparseGPRegression
        
    def get_C(self,Xtest):
        """
        Compute the value of the cloaking matrix, overrides DPGP and uses inducing inputs
        """

        test_cov = self.model.kern.K(Xtest,Xtest)
        sigmasqr = self.model.Gaussian_noise.variance[0]
        K_NN_diags = self.model.kern.Kdiag(self.model.X)
        K_NN = self.model.kern.K(self.model.X)
        
        K_star = self.model.kern.K(Xtest,self.model.Z.values)
        #print(self.model.Z.values)
        K_NM = self.model.kern.K(self.model.X,self.model.Z.values)
        K_MM = self.model.kern.K(self.model.Z.values)
        invK_MM = np.linalg.inv(K_MM)
        
        #lambda values are the diagonal of the training input covariances minus 
        #(cov of training+pseudo).(inv cov of pseudo).(transpose of cov of training+pseudo)
        lamb = np.zeros(len(self.model.X))
        for i,t_in in enumerate(self.model.X):
            lamb[i] = K_NN_diags[i] - np.dot(np.dot(K_NM[i,:].T,invK_MM),K_NM[i,:])

        #this finds (\Lambda + \sigma^2 I)^{-1}
        diag = 1.0/(lamb + sigmasqr) #diagonal values

        Q = K_MM + np.dot(K_NM.T * diag,K_NM)
        C = np.dot(np.dot(K_star, np.linalg.inv(Q)),K_NM.T) *  diag
        return C
    

