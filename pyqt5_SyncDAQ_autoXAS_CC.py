#! /usr/bin/env /home/uemura/Apps/anaconda3_2021Aprl/bin/python
import sys, os, string, io, glob, re, yaml, math, time
import numpy as np
import pandas as pd
import shutil
import subprocess as sub

import silx
from silx.gui import qt
app = qt.QApplication([])
import time
import silx.gui.colors as silxcolors
from silx.gui.plot import Plot1D
from joblib import Parallel, delayed

def CC2Eng(M):
    theta = M*4/10**6
    return 12.3984/(6.270832*np.sin(theta*np.pi/180.0))*1000

def msg(txt):
    _msg = qt.QMessageBox()
    _msg.setIcon(qt.QMessageBox.Warning)
    _msg.setText(txt)
    _msg.setStandardButtons(qt.QMessageBox.Ok)
    return _msg

try:
    import dbpy
    import stpy
except:
    msg('Fialed to import dbpy').exec_()
    sys.exit()

HOMEDIR = os.environ['HOME']
PYDIR = HOMEDIR+'/python'
PROGRAMDIR =  PYDIR+'/py_SyncDAQ_autoXAS_CC_dev'

wHDF5 = '/work/uemura/mpccd/hdf5'

maxcount = 50

#####read configulation file of SACLA equipments#####
Equipments_in_SACLA = yaml.load(open(PROGRAMDIR+'/SACLA_equiplist.txt'),Loader=yaml.Loader)['SACLA_eq_list']

from Ui_SyncDAQ_XASauto import Ui_MainWindow
from LedIndicatorWidget import *

class MainWindow(qt.QMainWindow):
    def __init__(self):
        # QtGui.QMainWindow.__init__(self,parent)
        super(self.__class__, self).__init__()
        self.u = Ui_MainWindow()
        self.u.setupUi(self)
        self.eqid = [True,True,True]
        self.motorlist = yaml.load(open(PROGRAMDIR+'/motorlist.yaml'),Loader=yaml.Loader)['eqid']
        self.eqid_ud = [ x +'/position' in Equipments_in_SACLA for x in self.motorlist]
        self.u.comboBox.addItems(self.motorlist)
        
        self.timer = qt.QBasicTimer()
        #self.timer.setInterval(_interval*1000)

        self.pdlist = ['xfel_bl_3_st_2_pd_user_1_fitting_peak/voltage',
                       'xfel_bl_3_st_2_pd_user_2_fitting_peak/voltage',
                       'xfel_bl_3_st_2_pd_user_3_fitting_peak/voltage',
                       'xfel_bl_3_st_2_pd_user_4_fitting_peak/voltage',
                       'xfel_bl_3_st_2_pd_user_5_fitting_peak/voltage',
                       'xfel_bl_3_st_2_pd_user_6_fitting_peak/voltage',
                       'xfel_bl_3_st_2_pd_user_7_fitting_peak/voltage',
                       'xfel_bl_3_st_2_pd_user_8_fitting_peak/voltage',
                       'xfel_bl_3_st_2_pd_user_9_fitting_peak/voltage',
                       'xfel_bl_3_st_2_pd_user_10_fitting_peak/voltage',
                       'xfel_bl_3_st_2_pd_user_11_fitting_peak/voltage',
                       'xfel_bl_3_st_2_pd_user_12_fitting_peak/voltage',
                       'xfel_bl_3_st_2_pd_user_13_fitting_peak/voltage',
                       'xfel_bl_3_st_2_pd_user_14_fitting_peak/voltage',
                       'xfel_bl_3_st_2_pd_user_15_fitting_peak/voltage']

        self.dbmonochro = 'xfel_bl_3_st_1_motor_3/position'
        self.confdir = PROGRAMDIR+'/Event_Conf'
        
        self.u.progressBar.setMaximum(self.u.sB_RN_end.value())
        self.u.progressBar.setMinimum(self.u.sB_RN_start.value())
        self.u.progressBar.setValue(self.u.progressBar.minimum())
        self.runNumber = self.u.sB_RN_start.value()
        self.runNumber_max = self.u.sB_RN_end.value()
        
        self.led = LedIndicator(self)
        layout = qt.QVBoxLayout()
        self.u.widget_3.setLayout(layout)
        layout.addWidget(self.led)

        ############ Plotters ############
        self.plot_xas = Plot1D()
        self.plot_intensity = Plot1D()
        
        layout = qt.QVBoxLayout()
        self.u.widget.setLayout(layout)
        layout.addWidget(self.plot_xas)
        
        layout = qt.QVBoxLayout()
        self.u.widget_2.setLayout(layout)
        layout.addWidget(self.plot_intensity)

        def chooseDatDir():
            _dir = self.u.textBrowser.toPlainText()
            self.u.textBrowser.clear()
            basedir = HOMEDIR
            if os.path.isdir(_dir):
                basedir = _dir

            datdir = qt.QFileDialog.getExistingDirectory(None, 'Select a folder:',
                                                            basedir, qt.QFileDialog.ShowDirsOnly)
            self.u.textBrowser.append(datdir.rstrip())
        def setvalue_start_number(value):
            self.runNumber = value
            #print (self.runnumber)
        def setvalue_end_number(value):
            self.runNumber_max = value
        self.u.pB_path.clicked.connect(chooseDatDir)
        self.u.sB_RN_start.valueChanged[int].connect(self.u.sB_RN_end.setMinimum)
        self.u.sB_RN_start.valueChanged[int].connect(self.u.progressBar.setMinimum)
        self.u.sB_RN_start.valueChanged[int].connect(self.u.progressBar.setValue)
        self.u.sB_RN_end.valueChanged[int].connect(self.u.progressBar.setMaximum)
        self.u.sB_RN_start.valueChanged[int].connect(setvalue_start_number)
        self.u.sB_RN_end.valueChanged[int].connect(setvalue_end_number)
        
        
        self.u.pB_run.clicked.connect(self.doAction)
        
        self.show()

    def timerEvent(self, e):
        if not self.led.isChecked():
            if self.u.lcdNumber_2.value() < maxcount:
                self.u.lcdNumber_2.display(self.u.lcdNumber_2.value()+1)
            else:
                RNUM_newest = dbpy.read_runnumber_newest(self.BL)
                if (self.runNumber < RNUM_newest) and (self.runNumber <= self.runNumber_max):
                    # self.runNumber = RNUM_newest
                    self.led.setChecked(True)
                    self.u.lcdNumber.display(self.runNumber)
                    self.process = 'take'
                    return
                elif self.runNumber > self.runNumber_max:
                    self.timer.stop()
                    self.u.progressBar.setValue(self.u.progressBar.maximum())
                    # self.runNumber = self.u.progressBar.minimum()
                    self.u.pB_run.setText('Run')
                    return
                self.u.lcdNumber_2.display(0)

        else:
            if self.process == 'take':
                _start = time.time()
                print(f"########## process starts ###########")
                self.led.setChecked(True)
                self.u.textBrowser_2.append('ready to convert run' + str(self.runNumber) + '...')
                if os.path.isdir(self.path_to_data + '/' + f"r{self.runNumber}"):
                    pass
                else:
                    os.mkdir(self.path_to_data + '/' + f'r{self.runNumber}')
                self.u.textBrowser_2.append('     #####' + str(self.runNumber) + ':' + 'taglist_all' + '#####')
                time.sleep(1)
                taglist_all = []
                filterlist = self.confdir + '/' + 'FEL_openshutter_beamon.txt'
                args = ['MakeTagList', '-r', str(self.runNumber), '-b', str(self.BL), '-inp', filterlist]
                P_MkTagList = sub.Popen(args, stdout=sub.PIPE)
                stdout, stderror = P_MkTagList.communicate()
                for term in io.StringIO(stdout.decode('utf-8')):
                    if re.match(r'^\d+$', term.rstrip()):
                        taglist_all.append(int(term.rstrip()))
                # print(taglist_all)
                self.u.textBrowser_2.append('     #####' + str(self.runNumber) + ':' + 'taglist_laseron' + '#####')
                # print('###MakeTagList for All: ' + str(time.time()-start))
                taglist_laseron = []
                filterlist = self.confdir + '/' + 'FEL_LH1_openshutter_beamon.txt'
                args = ['MakeTagList', '-r', str(self.runNumber), '-b', str(self.BL), '-inp', filterlist]
                P_MkTagList = sub.Popen(args, stdout=sub.PIPE)
                stdout, stderror = P_MkTagList.communicate()
                for term in io.StringIO(stdout.decode('utf-8')):
                    if re.match(r'^\d+$', term.rstrip()):
                        taglist_laseron.append(int(term.rstrip()))
                # print(taglist_laseron)
                if self.u.checkBox_wLaser.isChecked() and taglist_laseron and taglist_all:
                    taglist_laseroff = [x for x in taglist_all if not x in taglist_laseron]
                    ###for taglist:laser on###
                    taghi = dbpy.read_hightagnumber(self.BL, self.runNumber)
                    devlist = [self.dbmonochro,self.eqid+'/position']+[self.pdlist[num-1] for num in self.num_pdlist]
                    out = Parallel(n_jobs=5,backend='threading')(delayed(dbpy.read_syncdatalist)(d, taghi, tuple(taglist_laseron)) for d in devlist)
                    
                    df ={}
                    df['#Tag'] = np.array(taglist_laseron)
                    df['mono'] = np.array(out[0])
                    df['motor_1'] = np.array(out[1])
                    
                    for z, num in enumerate(self.num_pdlist):
                        df[f'pd_{num}'] = np.array(out[2+z])
                        
                    pd.DataFrame(
                            df
                        ).to_csv(self.path_to_data + '/' + f'r{self.runNumber}' + '/' + f'laseron_{self.runNumber}' + '.csv', index=False)

                    # print('###Extract data for Laser: ' + str(time.time()-start))
                    ###for taglist:laser off###
                    if self.u.checkBox_wLaser.isChecked() and taglist_laseroff and taglist_all:
                        taghi = dbpy.read_hightagnumber(self.BL, self.runNumber)
                        devlist = [self.dbmonochro,self.eqid+'/position']+[self.pdlist[num-1] for num in self.num_pdlist]
                        out = Parallel(n_jobs=5,backend='threading')(delayed(dbpy.read_syncdatalist)(d, taghi, tuple(taglist_laseroff)) for d in devlist)
                    
                        df ={}
                        df['#Tag'] = np.array(taglist_laseroff)
                        df['mono'] = np.array(out[0])
                        df['motor_1'] = np.array(out[1])
                    
                        for z, num in enumerate(self.num_pdlist):
                            df[f'pd_{num}'] = np.array(out[2+z])
                        
                        pd.DataFrame(
                            df
                        ).to_csv(self.path_to_data + '/' + f'r{self.runNumber}' + '/' + f'laseroff_{self.runNumber}' + '.csv' , index=False)

                    else:
                        print('    #####laseroff is empty#####')

                elif not self.u.checkBox_wLaser.isChecked() and taglist_all:
                    ###for taglist: all###
                    taghi = dbpy.read_hightagnumber(self.BL, self.runNumber)
                    devlist = [self.dbmonochro,self.eqid+'/position']+[self.pdlist[num-1] for num in self.num_pdlist]
                    out = Parallel(n_jobs=5,backend='threading')(delayed(dbpy.read_syncdatalist)(d, taghi, tuple(taglist_all)) for d in devlist)
                    
                    df ={}
                    df['#Tag'] = np.array(taglist_all)
                    df['mono'] = np.array(out[0])
                    df['motor_1'] = np.array(out[1])
                    
                    for z, num in enumerate(self.num_pdlist):
                        df[f'pd_{num}'] = np.array(out[2+z])
                        
                    pd.DataFrame(
                            df
                        ).to_csv(self.path_to_data + '/' + f'r{self.runNumber}' + '/' + f'laserall_{self.runNumber}' + '.csv' , index=False)
                print(f"########## process ends: {time.time() - _start:.1f} s ###########")
                self.u.textBrowser_2.append(f"     ########## process ends: {time.time() - _start:.1f} s ###########")
                self.process = 'process'
            elif self.process == 'process':
                ###### Post processing #####
                sI0_1, sI0_2, sIf = f'pd_{self.num_pdlist[0]}', f'pd_{self.num_pdlist[1]}', f'pd_{self.num_pdlist[2]}'
                I0_ll, I0_ul, If_ll, If_ul = self.u.dsb_I0_ll.value(), self.u.dsb_I0_ul.value(), self.u.dsb_If_ll.value(), self.u.dsb_If_ul.value()


                if self.u.checkBox_wLaser.isChecked():
                    self.u.textBrowser_2.append("     >>>>>>>>>> Post processing <<<<<<<<<<")
                    self.u.textBrowser_2.append('     ########## Laser Off ##########')
                    df = pd.read_csv(self.path_to_data + '/' + f'r{self.runNumber}' + f'/laseroff_{self.runNumber}.csv')

                    _df = {
                        'Tag': [],
                        'mono': [],
                        'motor_1': [],
                        sI0_1: [],
                        sI0_2: [],
                        sIf: [],
                    }

                    for i, tag in enumerate(df['#Tag'].values):
                        _df['Tag'].append(tag)
                        _df['mono'].append(int(df['mono'].values[i].replace('pulse', '')))
                        _df['motor_1'].append(int(df['motor_1'].values[i].replace('pulse', '')))

                        ######### pd: I0_1 ##########
                        if ('not-converged' in df[sI0_1].values[i]) or ('saturated' in df[sI0_1].values[i]):
                            _df[sI0_1].append(np.nan)
                        else:
                            _df[sI0_1].append(float(df[sI0_1].values[i].replace('V', '')))

                        ######### pd: I0_2 ##########
                        if ('not-converged' in df[sI0_2].values[i]) or ('saturated' in df[sI0_2].values[i]):
                            _df[sI0_2].append(np.nan)
                        else:
                            _df[sI0_2].append(float(df[sI0_2].values[i].replace('V', '')))

                        ######### pd: If ##########
                        if ('not-converged' in df[sIf].values[i]) or ('saturated' in df[sIf].values[i]):
                            _df[sIf].append(np.nan)
                        else:
                            _df[sIf].append(float(df[sIf].values[i].replace('V', '')))

                    data_off = pd.DataFrame(
                        {
                            'mono': np.array(_df['mono']),
                            'motor_1': np.array(_df['motor_1']),
                            'I0': (np.array(_df[sI0_1]) + np.array(_df[sI0_2]))/2,
                            'If': np.array(_df[sIf])
                        },
                        index=_df['Tag']
                    )

                    self.u.textBrowser_2.append('     ########## Laser On ##########')
                    df = pd.read_csv(self.path_to_data + '/' + f'r{self.runNumber}' + f'/laseron_{self.runNumber}.csv')

                    _df = {
                        'Tag': [],
                        'mono': [],
                        'motor_1': [],
                        sI0_1: [],
                        sI0_2: [],
                        sIf: [],
                    }

                    for i, tag in enumerate(df['#Tag'].values):
                        _df['Tag'].append(tag)
                        _df['mono'].append(int(df['mono'].values[i].replace('pulse', '')))
                        _df['motor_1'].append(int(df['motor_1'].values[i].replace('pulse', '')))

                        ######### pd: I0_1 ##########
                        if ('not-converged' in df[sI0_1].values[i]) or ('saturated' in df[sI0_1].values[i]):
                            _df[sI0_1].append(np.nan)
                        else:
                            _df[sI0_1].append(float(df[sI0_1].values[i].replace('V', '')))

                        ######### pd: I0_2 ##########
                        if ('not-converged' in df[sI0_2].values[i]) or ('saturated' in df[sI0_2].values[i]):
                            _df[sI0_2].append(np.nan)
                        else:
                            _df[sI0_2].append(float(df[sI0_2].values[i].replace('V', '')))

                        ######### pd: If ##########
                        if ('not-converged' in df[sIf].values[i]) or ('saturated' in df[sIf].values[i]):
                            _df[sIf].append(np.nan)
                        else:
                            _df[sIf].append(float(df[sIf].values[i].replace('V', '')))

                    data_on = pd.DataFrame(
                        {
                            'mono': np.array(_df['mono']),
                            'motor_1': np.array(_df['motor_1']),
                            'I0': (np.array(_df[sI0_1]) + np.array(_df[sI0_2]))/2,
                            'If': np.array(_df[sIf])
                        },
                        index=_df['Tag']
                    )

                    self.monos = np.unique(data_on['mono'].values)
                    self.motor = np.unique(data_on['motor_1'].values)

                    xas_on, xas_off, err_on, err_off = [], [], [], []
                    I0_on, I0_off, If_on, If_off = [], [], [], []
                    if self.monos.size > 2:
                        for m in self.monos:
                            Izero = data_off['I0'].values[data_off['mono'].values == m]
                            Iflo = data_off['If'].values[data_off['mono'].values == m]
                            TF = (~np.isnan(Izero)) * (
                                        ~np.isnan(Iflo) * (Izero > I0_ll) * (Izero < I0_ul) * (Iflo > If_ll) * (
                                            Iflo < If_ul))
                            xas_off.append(Iflo[TF].sum() / Izero[TF].sum())
                            std, N = np.std(Iflo[TF] / Izero[TF]), (TF * 1).sum()
                            err_off.append(std / np.sqrt(N))

                            I0_off.append(Izero[TF].sum())
                            If_off.append(Iflo[TF].sum())

                            Izero = data_on['I0'].values[data_on['mono'].values == m]
                            Iflo = data_on['If'].values[data_on['mono'].values == m]
                            TF = (~np.isnan(Izero)) * (
                                        ~np.isnan(Iflo) * (Izero > I0_ll) * (Izero < I0_ul) * (Iflo > If_ll) * (
                                            Iflo < If_ul))
                            xas_on.append(Iflo[TF].sum() / Izero[TF].sum())
                            std, N = np.std(Iflo[TF] / Izero[TF]), (TF * 1).sum()
                            err_on.append(std / np.sqrt(N))

                            I0_on.append(Izero[TF].sum())
                            If_on.append(Iflo[TF].sum())
                    else:
                        for m in self.motor:
                            Izero = data_off['I0'].values[data_off['motor_1'].values == m]
                            Iflo = data_off['If'].values[data_off['motor_1'].values == m]
                            TF = (~np.isnan(Izero)) * (
                                        ~np.isnan(Iflo) * (Izero > I0_ll) * (Izero < I0_ul) * (Iflo > If_ll) * (
                                            Iflo < If_ul))
                            xas_off.append(Iflo[TF].sum() / Izero[TF].sum())
                            std, N = np.std(Iflo[TF] / Izero[TF]), (TF * 1).sum()
                            err_off.append(std / np.sqrt(N))

                            I0_off.append(Izero[TF].sum())
                            If_off.append(Iflo[TF].sum())

                            Izero = data_on['I0'].values[data_on['motor_1'].values == m]
                            Iflo = data_on['If'].values[data_on['motor_1'].values == m]
                            TF = (~np.isnan(Izero)) * (
                                        ~np.isnan(Iflo) * (Izero > I0_ll) * (Izero < I0_ul) * (Iflo > If_ll) * (
                                            Iflo < If_ul))
                            xas_on.append(Iflo[TF].sum() / Izero[TF].sum())
                            std, N = np.std(Iflo[TF] / Izero[TF]), (TF * 1).sum()
                            err_on.append(std / np.sqrt(N))

                            I0_on.append(Izero[TF].sum())
                            If_on.append(Iflo[TF].sum())

                    self.xas_off = np.array(xas_off)
                    self.xas_on = np.array(xas_on)
                    self.err_off = np.array(err_off)
                    self.err_on = np.array(err_on)

                    self.I0_on, self.I0_off,self.If_on, self.If_off = np.array(I0_on),np.array(I0_off),np.array(If_on),np.array(If_off)
                    self.process = 'plot'
                else:
                    self.process = 'None'
                    self.led.setChecked(False)
                    self.runNumber += 1

            elif self.process == 'plot':

                if self.monos.size > 2:
                    self.plot_xas.clear()
                    self.plot_intensity.clear()
                    self.plot_xas.addCurve(CC2Eng(self.monos), self.xas_off,linewidth=2,legend='Off')
                    self.plot_xas.addCurve(CC2Eng(self.monos), self.xas_on,linewidth=2,legend='On')
                    self.plot_xas.setGraphXLabel('Energy /eV')
                    self.plot_xas.setGraphYLabel('XAS')
                    self.plot_xas.setGraphYLabel('$\Delta$XAS',axis='right')
                    self.plot_xas.addCurve(CC2Eng(self.monos), self.xas_on-self.xas_off, yaxis='right', linewidth=2, legend='diff')

                    self.plot_intensity.addCurve(CC2Eng(self.monos),self.I0_off,linewidth=2,legend='I0: off')
                    self.plot_intensity.addCurve(CC2Eng(self.monos), self.I0_on,linewidth=2, legend='I0: on')
                    self.plot_intensity.addCurve(CC2Eng(self.monos), self.If_off,yaxis='right', linewidth=2, legend='If: off')
                    self.plot_intensity.addCurve(CC2Eng(self.monos), self.If_on,yaxis='right', linewidth=2, legend='If: on')
                    self.plot_intensity.setGraphXLabel('Energy /eV')
                    self.plot_intensity.setGraphYLabel('I0')
                    self.plot_intensity.setGraphYLabel('If',axis='right')

                    self.plot_xas.setGraphTitle(f'run{self.runNumber}')
                    self.plot_intensity.setGraphTitle(f'run{self.runNumber}')

                    pd.DataFrame(
                        {
                            '#CC': self.monos,
                            'Energy': CC2Eng(self.monos),
                            'xas_on': self.xas_on,
                            'xas_off': self.xas_off,
                            'err_on': self.err_on,
                            'err_off': self.err_off,

                        }
                    ).to_csv(self.path_to_data + '/' + f'r{self.runNumber}' + f'/r{self.runNumber}_escan.csv',
                             sep=' ', index=False)
                else:
                    self.plot_xas.clear()
                    self.plot_intensity.clear()
                    self.plot_xas.addCurve(self.motor, self.xas_off, linewidth=2, legend='Off')
                    self.plot_xas.addCurve(self.motor, self.xas_on, linewidth=2, legend='On')
                    self.plot_xas.setGraphXLabel('motor /pls')
                    self.plot_xas.setGraphYLabel('XAS')
                    self.plot_xas.setGraphYLabel('$\Delta$XAS', axis='right')
                    self.plot_xas.addCurve(self.motor, self.xas_on - self.xas_off, yaxis='right', linewidth=2,
                                           legend='diff')
                    self.plot_intensity.addCurve(self.motor, self.I0_off, linewidth=2, legend='I0: off')
                    self.plot_intensity.addCurve(self.motor, self.I0_on, linewidth=2, legend='I0: on')
                    self.plot_intensity.addCurve(self.motor, self.If_off, yaxis='right', linewidth=2,
                                                 legend='If: off')
                    self.plot_intensity.addCurve(self.motor, self.If_on, yaxis='right', linewidth=2,
                                                 legend='If: on')
                    self.plot_intensity.setGraphXLabel('motor /pls')
                    self.plot_intensity.setGraphYLabel('I0')
                    self.plot_intensity.setGraphYLabel('If', axis='right')

                    self.plot_xas.setGraphTitle(f'run{self.runNumber}')
                    self.plot_intensity.setGraphTitle(f'run{self.runNumber}')

                    pd.DataFrame(
                        {
                            '#motor': self.motor,
                            'xas_on': self.xas_on,
                            'xas_off': self.xas_off,
                            'err_on': self.err_on,
                            'err_off': self.err_off
                        }
                    ).to_csv(self.path_to_data + '/' + f'r{self.runNumber}' + f'/r{self.runNumber}_mscan.csv',
                             sep=' ', index=False)
                self.plot_xas.saveGraph(self.path_to_data + '/' + f'r{self.runNumber}' + f'/r{self.runNumber}_plot.png')

                self.runNumber += 1
                self.u.progressBar.setValue(self.runNumber - 1)
                self.process = 'None'
                self.led.setChecked(False)
                self.u.lcdNumber_2.display(0)

    def doAction(self):
        if self.timer.isActive():
            self.timer.stop()
            self.u.progressBar.setValue(self.u.progressBar.maximum())
            self.u.pB_run.setText('Run')
            self.runNumber = self.u.progressBar.minimum()
        else:
            if os.path.isdir(self.u.textBrowser.toPlainText()):
                self.BL = self.u.sB_BL.value()
                self.runNumber = self.u.sB_RN_start.value()
                self.runNumber_max = self.u.sB_RN_end.value()
                self.u.progressBar.setMinimum(self.u.sB_RN_start.value())
                self.u.progressBar.setMaximum(self.u.sB_RN_end.value())

                self.num_pdlist = [j for j in range(1,16) if getattr(self.u,f"pdI0_{j}").isChecked()]+ \
                                  [j for j in range(1, 16) if getattr(self.u, f"pdI_{j}").isChecked()]
                self.path_to_data = self.u.textBrowser.toPlainText()
                self.eqid = self.u.comboBox.currentText()
                self.u.textBrowser_2.clear()
                self.u.lcdNumber_2.display(0)
                self.led.setChecked(False)
                self.process = 'None' # take or process or plot
                self.timer.start(100,self)
                self.u.pB_run.setText('Stop')
            else:
                msg('Output is not set').exec_()
                


if __name__ == '__main__':
    wid = MainWindow()
    wid.setWindowTitle('SyncDAQ_autoXAS')
    sys.exit(app.exec_())
