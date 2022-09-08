import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv('trap_df.csv',index_col=0)

print(df.keys())

iterations = 10

# for i in range(iterations):
#     try:
#         # print(df['start_amp_{}'.format(i)])
#         plt.errorbar(df['freq_MHz'],df['multi_{}_I0'.format(i)],yerr=df['multi_{}_I0_err'.format(i)],fmt='o',label=i,c='C{}'.format(i))
#         plt.plot(df['freq_MHz'],df['multi_{}_I0'.format(i)],c='C{}'.format(i))
#         print('{}:'.format(i),(df['multi_{}_I0'.format(i)]-df['multi_0_I0'].mean()).abs().sum(),list(df['start_amp_{}'.format(i)]))
#     except KeyError:
#         pass

for i in range(iterations):
    try:
        # print(df['start_amp_{}'.format(i)])
        plt.scatter(df.index,df['iteration_{}_peak'.format(i)],c='C{}'.format(i),label=i)
        plt.plot(df.index,df['iteration_{}_peak'.format(i)],c='C{}'.format(i))
        print('{}:'.format(i),(df['multi_{}_I0'.format(i)]-df['multi_0_I0'].mean()).abs().sum(),list(df['start_amp_{}'.format(i)]))
    except KeyError:
        pass
    
plt.axhline(df['iteration_0_peak'].mean(),c='C0',linestyle='--')
    
plt.legend(title='iteration')
plt.xlabel('trap')
plt.ylabel('fitted intensity (arb.)')
plt.xticks([0,1,2,3])
plt.show()

foms = []
for i in range(iterations):
    try:
        plt.scatter(i,(df['multi_{}_I0'.format(i)]-df['multi_0_I0'].mean()).abs().sum()/df['multi_0_I0'].mean()/len(df),c='C{}'.format(i))
    except KeyError:
        pass
plt.xticks(list(range(iterations)))
plt.xlabel('iteration')
plt.ylabel('figure of merit')
plt.show()

plt.scatter(df['freq_MHz'],df['start_amp_9'],c='C9')
plt.plot(df['freq_MHz'],df['start_amp_9'],c='C9')
plt.axhline(df['start_amp_9'].mean(),c='C9',linestyle='--')
plt.xlabel('frequency (MHz)')
plt.ylabel('corrected start_amp_9',color='C9')

ax2 = plt.gca().twinx()
# make a plot with different y-axis using second axis object
ax2.scatter(df['freq_MHz'], df['multi_0_I0'])
ax2.plot(df['freq_MHz'], df['multi_0_I0'])
ax2.axhline(df['multi_0_I0'].mean(),c='C0',linestyle='--')
ax2.set_ylabel("uncorrected intensity (arb.)",color="C0")
plt.show()

plt.scatter(df['freq_MHz'],np.log10(df['start_amp_3']/df['start_amp_0'])/np.log10(df['multi_0_I0']/df['multi_0_I0'].mean()),c='C3')

plt.show()