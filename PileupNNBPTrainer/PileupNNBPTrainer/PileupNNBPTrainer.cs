using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Diagnostics;
using System.Drawing;
using System.Text;
using System.Windows.Forms;
using System.IO;
using System.Collections;


namespace PileupNNBPTrainer
{
    public partial class PileupNNBPTrainer : Form
    {
        public struct Energy
        {
            public double[] en;
            public double tm;
            public int plsPtr;
        }
        public struct PulseData2    
        {
            public int isPileup;
            public PointF peak;
            public int[] pos;
            public double[] nnIn;
            public PointF[] pts;
        }
        public struct PulseData
        {
            public int isPileup;
            public int peakPos;
            public double peakVal;
            public double[] pts;
            public double[] nnIn;
        }
        public struct ChannelInfo
        {
            public string name;
            public int height;
            public int count;
            public int span;
            public short[] profile;
        }
        //******************************************************
        //GLOBAL VARAIBLE//
        public ArrayList alIn;
        public ArrayList alOut;
        public ArrayList ldPulseData;
        public string dirPath;
        public string netFlnm;
        NnBP nnbp;
        public Graphics g;
        public Bitmap bmp;
        public int testCnt;
        public Energy energy;
        //public int plsPtr = 0;
        public int plsCount = 0;
        public Random rnd = new Random(DateTime.Now.Millisecond);
        public string svflnm;
        public string ldflnm;
        public double[] energiesArr;
        public Config cnfg;
        public string cfgFlnm = "config.csv";
        int loop = 0;
        int flno = 0;
        public string[] flnmLst;
        PulseData2[][] pulsedata2;
        int xmx = -1;
        int x1 = -1;
        int x2 = -1;
        int x3 = -1;
        int pileUpPro = 10;//pile up probability is 1/10;
        bool pileUpFlg = false;//pile up flag;
        int scanCount = 0;
        int[] chnErr;
        string testCsvFlnm;
        string test2CsvStr;
        int puno = 0;
        ChannelInfo[] chnlinfo;
        string cfgFlnmMCA = "configMCA.csv";
        int channels = 4096;
        int count = 1000;
        int span = 1000;
        int chMx = 8;
        //******************************************************
        public PileupNNBPTrainer()
        {
            InitializeComponent();
            nnbp = new NnBP();
            energy = new Energy();
            energy.en = new double[2];
            energiesArr = new double[3];
            energiesArr[0] = 0.2;
            energiesArr[1] = 0.7;
            energiesArr[2] = 0.5;
            cfgFlnm = Application.StartupPath + @"\config.csv";
            chnErr = new int[4096];
            cfgFlnmMCA = Application.StartupPath + @"\configMca.csv";
            LoadParameters(cfgFlnmMCA);
        }
        //***********************************************************
        private void LoadParameters(string flnm)
        {
            //f{x)=a*exp(-(x-b)^2/(2*c^2))
            double[] yy = new double[channels];
            for (int i = 0; i < channels; i++)
            {
                yy[i] = Math.Exp(-(i - channels / 2.0) * (i - channels / 2.0) / (channels * channels * 0.05));
            }
            //string[] lines = cfgDt.Split('\n');
            string[] lines = File.ReadAllLines(flnm);
            channels = System.Convert.ToInt16(lines[1].Split(',')[1]);
            count = System.Convert.ToInt16(lines[1].Split(',')[2]);
            span = System.Convert.ToInt16(lines[1].Split(',')[3]);
            chMx = lines.Length - 2;
            chnlinfo = new ChannelInfo[chMx];
            for (int i = 0; i < chMx; i++)
            {
                string[] wrds = lines[i + 2].Split(',');
                chnlinfo[i].name = wrds[0];
                chnlinfo[i].height = System.Convert.ToInt16(wrds[1]);
                chnlinfo[i].count = System.Convert.ToInt16(wrds[2]);
                chnlinfo[i].span = System.Convert.ToInt16(wrds[3]);
                double yk = (double)(yy.Length / (chnlinfo[i].span + 1));
                ArrayList al = new ArrayList();
                for (short j = 0; j < chnlinfo[i].span; j++)
                {
                    int sz = (short)(1000 * yy[(int)((j + 1) * yk)]);
                    for (int k = 0; k < sz; k++)
                    {
                        al.Add(j);
                    }
                }
                chnlinfo[i].profile = new short[al.Count];
                for (int j = 0; j < al.Count; j++)
                {
                    chnlinfo[i].profile[j] = (short)((short)al[j] - ((short)chnlinfo[i].span / (short)2));
                }
            }
        }
        //******************************************************
        private void PileupNNBPTrainer_Shown(object sender, EventArgs e)
        {
            dirPath = Application.StartupPath;
            this.Location = new Point(10, 10);
            cnfg = new Config();
            cnfg.pileupNNBPtrainer = this;
            cnfg.Location = new Point(this.Location.X + this.Width, this.Location.Y);
            cnfg.Hide();
            this.Focus();
            bmp = new Bitmap(pBx1.Width, pBx1.Height);
            g = Graphics.FromImage(bmp);
            g.Clear(Color.Black);
            g.Dispose();
            pBx1.Image = bmp;
            cnfg.Location = new Point(this.Location.X + this.Width, this.Location.Y);
        }
        //******************************************************
        private void btnExit_Click(object sender, EventArgs e)
        {
            this.Close();
        }
        //******************************************************
        private void btnLoadNet_Click(object sender, EventArgs e)
        {
            string strPath = "";
            if (RadbtnPeak.Checked)
            {
                strPath = "PlsPeakDt.net";
            }
            if (RadbtnPileup.Checked)
            {
                strPath = "PlsDt.net";
            }
            lblTest.Text = "LoadNet";
            openFileDialog1.InitialDirectory = dirPath;
            openFileDialog1.FileName = strPath;
            openFileDialog1.Filter = "Net (*.Net;)|*.net|" + "All files (*.*)|*.*";
            openFileDialog1.Multiselect = false;
            openFileDialog1.Title = "Select Net Files - Pileup";
            if (DialogResult.Cancel == openFileDialog1.ShowDialog()) return;
            netFlnm = openFileDialog1.FileName;
            nnbp.LoadNet(netFlnm);
        }
        //******************************************************
        private void btnSaveNet_Click(object sender, EventArgs e)
        {
            lblTest.Text = "SaveNet";
            saveFileDialog1.InitialDirectory = dirPath;
            saveFileDialog1.Filter = "Net (*.Net;)|*.net|" + "All files (*.*)|*.*";
            saveFileDialog1.Title = "Save Net File - Pileup";
            if (DialogResult.Cancel == saveFileDialog1.ShowDialog()) return;
            netFlnm = saveFileDialog1.FileName;
            string[] words = netFlnm.Split(new Char[] { '.' });
            string s1 = words[words.Length - 1];
            if (s1 != "net")
                netFlnm = netFlnm + ".net";
            nnbp.SaveNet(netFlnm);
        }
        //******************************************************
        private void btnNewNet_Click(object sender, EventArgs e)
        {
            nnbp.load_random_weight();
            lblTest.Text = "NewNet";
        }
        //******************************************************
        private void btnTngStart_Click(object sender, EventArgs e)
        {
            if (btnTngStart.Text == "Tng Start")
            {
                btnTngStart.Text = "Tng Stop";
                timer2.Interval = 1;
                timer2.Start();
                testCnt = 0;
                lblTest.Text = "TngStart:" + testCnt.ToString();
            }
            else
            {
                btnTngStart.Text = "Tng Start";
                timer2.Stop();
                lblTest.Text = "TngStop:" + testCnt.ToString();
            }
            //minErr = 99999;
        }
        //******************************************************
        private void btnTestWave_Click(object sender, EventArgs e)
        {
            if (RadbtnPeak.Checked)
            {
                //double error = 0;
                int i = 0;
                int j = 0;
                for (; ; )
                {
                    i = rnd.Next(pulsedata2.Length);
                    j = rnd.Next(pulsedata2[i].Length);
                    if (pulsedata2[i][j].isPileup == 0)
                        break;
                }
                //ReNormalizeYi(pulsedata2[i][j].nnIn);
                for (int k = 0; k < pulsedata2[i][j].nnIn.Length; k++)
                {
                    nnbp.yi[k] = pulsedata2[i][j].nnIn[k];
                }
                int npk = pulsedata2[i][j].pos[0];
                int nmn = pulsedata2[i][j].pos[1];
                int nmx = pulsedata2[i][j].pos[pulsedata2[i][j].pos.Length - 1];
                nnbp.outk[0] = (double)(nmx - npk) / (nmx - nmn);
                nnbp.outk[1] = pulsedata2[i][j].peak.Y;
                double[] err = nnbp.UpdateNetErrors();//in %
                int errN = (int)(err[1] * 4096);
                chnErr[errN]++;
                lblTest.Text = errN.ToString() + " Chn";
                PulsePlotPeakTest(i, j, nnbp.yk);
            }
            if (RadbtnPileup.Checked)
            {
                double error = 0;
                int i = rnd.Next(pulsedata2.Length);
                int j = rnd.Next(pulsedata2[i].Length);
                //ReNormalizeYi(pulsedata2[i][j].nnIn);
                for (int k = 0; k < pulsedata2[i][j].nnIn.Length; k++)
                {
                    nnbp.yi[k] = pulsedata2[i][j].nnIn[k];
                }
                if (pulsedata2[i][j].isPileup == 0)
                {
                    nnbp.outk[0] = 0;
                    nnbp.outk[1] = 1;
                }
                else
                {
                    nnbp.outk[0] = 1;
                    nnbp.outk[1] = 0;
                }
                error = nnbp.UpdateNet();
                error = Math.Round(error, 3);
                lblTest.Text = error.ToString();
                PulsePlotTest(i, j, nnbp.yk);
            }
           
        }
        //******************************************************
        private void timer2_Tick(object sender, EventArgs e)
        {
            lblTest.Text = "TngStart:" + testCnt.ToString();
            testCnt++;
            if (RadbtnPeak.Checked)
            {
                TrainPeakValNNBP();
            }
            if (RadbtnPileup.Checked)
            {
                TrainPileupNNBP();
            }
        }
        //******************************************************
        private void TrainPileupNNBP()
        {
            double error = 0;
            for (int i = 0; i < pulsedata2.Length; i++)
            {
                for (int j = 0; j < pulsedata2[i].Length; j++)
                {
//                    ReNormalizeYi(pulsedata2[i][j].nnIn);
                    for (int k = 0; k < pulsedata2[i][j].nnIn.Length; k++)
                    {
                        nnbp.yi[k] = pulsedata2[i][j].nnIn[k];
                    }
                    if (pulsedata2[i][j].isPileup == 0)
                    {
                        nnbp.outk[0] = 0;
                        nnbp.outk[1] = 1;
                    }
                    else
                    {
                        nnbp.outk[0] = 1;
                        nnbp.outk[1] = 0;
                    }
                    double err = nnbp.UpdateNet();
                    error += err;
                    nnbp.update_and_correct_error();
                }
            }
            lblTest.Text = error.ToString();
        }
        //******************************************************
        private void TrainPeakValNNBP()
        {
            double error = 0;
            for (int i = 0; i < pulsedata2.Length; i++)
            {
                for (int j = 0; j < pulsedata2[i].Length; j++)
                {
                    if (pulsedata2[i][j].isPileup == 0)
                    {
                        //ReNormalizeYi(pulsedata2[i][j].nnIn);
                        for (int k = 0; k < pulsedata2[i][j].nnIn.Length; k++)
                        {
                            nnbp.yi[k] = pulsedata2[i][j].nnIn[k];
                        }
                        int npk= pulsedata2[i][j].pos[0];
                        int nmn = pulsedata2[i][j].pos[1];
                        int nmx = pulsedata2[i][j].pos[pulsedata2[i][j].pos.Length - 1];
                        nnbp.outk[0] = (double)(nmx - npk) / (nmx - nmn);
                        nnbp.outk[1] = pulsedata2[i][j].peak.Y;
                        double[] err = nnbp.UpdateNetErrors();
                        error += (int)(err[1]*4096);
                        nnbp.update_and_correct_error();
                    }
                }
            }
            int loops = pulsedata2.Length * pulsedata2[0].Length;
            double er = Math.Round(error / loops, 5);
            lblTest.Text = er.ToString()+" Chn";
        }
        //******************************************************
        private void PulseBtn_Click(object sender, EventArgs e)
        {
            if (PulseBtn.Text == "SimStart")
            {
                lblTest.Text = "Sim.Start";
                PulseBtn.Text = "SimStop";
                alIn = new ArrayList();
                alOut = new ArrayList();
                //PulsePlot();
                if (SavePulseDataChkBx.Checked == true)
                {
                    saveFileDialog1.InitialDirectory = dirPath;
                    saveFileDialog1.Filter = "TEXT (*.txt;)|*.txt|" + "All files (*.*)|*.*";
                    saveFileDialog1.Title = "Save Pulse Data File - Pileup";
                    if (DialogResult.Cancel == saveFileDialog1.ShowDialog()) return;
                    svflnm = saveFileDialog1.FileName;
                }
                bmp = new Bitmap(pBx1.Width / 3, pBx1.Height);
                g = Graphics.FromImage(bmp);
                g.Clear(Color.Black);
                g.Dispose();
                timer1.Interval = 100;
                timer1.Start();
                flno = 1;
                loop = 0;
                puno = 0;
            }
            else
            {
                lblTest.Text = " ";
                PulseBtn.Text = "SimStart";
                timer1.Stop();
            }
        }
        //******************************************************
        private void PulsePlot(Energy enrg, bool pileup)
        {
            bmp = new Bitmap(pBx1.Width/3, pBx1.Height);
            g = Graphics.FromImage(bmp);
            g.Clear(Color.Black);
            PointF[] pts1 = Energy2Array(enrg, pileup);
            PointF[] pts2 = Array2Shape(pts1);
            pts2 = Array2Shape(pts2);
            pts2 = Array2Shape(pts2);
            xmx = 0;
            int xs = -1;
            int xe = -1;
            float yt = bmp.Height * 0.05f;
            float ymx = int.MinValue;
            
            for (int x = 0; x < pts2.Length; x++)
            {
                if (ymx < pts2[x].Y)
                {
                    xmx = x;
                    ymx = pts2[x].Y;
                }
            }
            yt = (ymx * 0.05f)                                              ;
            for (int x = 0; x < pts2.Length; x++)
            {
                if (xs < 0)
                {
                    if (pts2[x].Y > yt)
                        xs = x;
                }
                else
                {
                    if (xe < 0)
                    {
                        if (pts2[x].Y <= yt)
                            xe = x;
                    }
                }
            }
            int xw = (xe - xs) / 4;
            x1 = xs + rnd.Next(xw);
            x2 = x1 + xw;
            x3 = x2 + xw;
            g.DrawLine(Pens.Blue, xmx, pts2[xmx].Y, xmx, 0);
            g.DrawLine(Pens.Blue, xs, pts2[xs].Y, xs, 0);
            g.DrawLine(Pens.Blue, xe, pts2[xe].Y, xe, 0);
            g.DrawLine(Pens.Green, x1, pts2[x1].Y, x1, 0);
            g.DrawLine(Pens.Green, x2, pts2[x2].Y, x2, 0);
            g.DrawLine(Pens.Green, x3, pts2[x3].Y, x3, 0);
            g.DrawLines(pileup ? Pens.Red : Pens.Yellow, pts2);
            g.Dispose();
            bmp.RotateFlip(RotateFlipType.RotateNoneFlipY);
            pBx1.Image = bmp;
            if (SavePulseDataChkBx.Checked == true)
                SavePulse2File2(svflnm, pileup, pts2);
        }
        //******************************************************
        private void PulsePlotTest(int i, int j, double[] yk)
        {
            bmp = new Bitmap(pBx1.Width / 3, pBx1.Height);
            Pen pn = new Pen(Color.Blue);
            if ((yk[0] > 0.5) & (yk[1] < 0.5))
            {
                pn = Pens.Red;
            }
            if ((yk[0] < 0.5) & (yk[1] > 0.5))
            {
                pn = Pens.Yellow;
            }
            if ((yk[0] < 0.5) & (yk[1] < 0.5))
            {
                pn = Pens.Blue;
            }
            if ((yk[0] > 0.5) & (yk[1] > 0.5))
            {
                pn = Pens.Blue;
            }

            //bmp = new Bitmap(pBx1.Width, pBx1.Height);
            g = Graphics.FromImage(bmp);
            g.Clear(Color.Black);
            g.DrawLines(pn, pulsedata2[i][j].pts);
            g.Dispose();
            bmp.RotateFlip(RotateFlipType.RotateNoneFlipY);
            pBx1.Image = bmp;
        }
        //*******************************************************
        private void SavePulse2File(string flnm, bool pileup, int[] ptsPtrs, double[] ptsDt)
        {
            string sno=flno.ToString().PadLeft(3,'0');
            flnm = flnm.Replace(".txt", sno + ".txt");
            StreamWriter sw = new StreamWriter(flnm, true);//true for append
            string str = "";
            if (pileup)
            {
                str += "1";
            }
            else
            {
                str += "0";
                puno++;
            }
            str += "," + ptsPtrs[0].ToString() + "," + ptsPtrs[1].ToString() + "," + ptsPtrs[2].ToString() + "," + ptsPtrs[3].ToString() + "," + ptsPtrs[4].ToString();
            str += ":";
            for (int i = 0; i < ptsDt.Length; i++)
            {
                float yInv = (float)Math.Round(ptsDt[i], 4);
                str += yInv.ToString() + ",";
            }
            str = str.TrimEnd(',');
            sw.WriteLine(str);
            sw.Close();
            loop++;
            //if (loop>=100)
            if (puno >= 100)
            {
                flno++;
                if (flno > 100)
                {
                    timer1.Stop();
                    return;
                }
                loop = 0;
                puno = 0;
                lblTest.Text = flno.ToString();
            }
        }
        //******************c************************************
        private void SavePulse2File2(string flnm, bool pileup, PointF[] ptsSave)
        {
            string sno = flno.ToString().PadLeft(3, '0');
            flnm = flnm.Replace(".txt", sno + ".txt");
            StreamWriter sw = new StreamWriter(flnm, true);//true for append
            string str = "";
            if (pileup)
                str += "1";
            else
                str += "0";
            str += "," + xmx.ToString() + "," + x1.ToString() + "," + x2.ToString() + "," + x3.ToString();
            for (int i = 0; i < ptsSave.Length; i++)
            {
                str += ":";
                float yInv = pBx1.Height - ptsSave[i].Y;
                str += ptsSave[i].X.ToString() + "," + yInv.ToString();
            }
            sw.WriteLine(str);
            sw.Close();
            loop++;
            if (loop >= 100)
            {
                flno++;
                if (flno > 100)
                {
                    timer1.Stop();
                    return;
                }
                loop = 0;
                //  PulseBtn.Text = "SimStart";
                //  timer1.Stop();
                //MessageBox.Show("Save");
                lblTest.Text = flno.ToString();
            }
        }
        //******************c************************************
        private PointF[] Array2Shape(PointF[] pts)
        {
            double Vc = 0;
            double res=0.01;
            PointF[] ptsOut = new PointF[pts.Length];
            for (int i = 0; i < pts.Length; i++)
            {
                for (int j = 0; j < 10; j++)
                {
                    Vc += ((pts[i].Y) - Vc) * res;
                }
                ptsOut[i].X = i;
                ptsOut[i].Y = (float)Vc;
            }
            return ptsOut;
        }
        //******************c************************************
        private double[] Array2ShapeDbl(double[] pts)
        {
            double Vc = 0;
            double res = 0.01;
            double[] ptsOut = new double[pts.Length];
            for (int i = 0; i < pts.Length; i++)
            {
                for (int j = 0; j < 10; j++)
                {
                    Vc += ((pts[i]) - Vc) * res;
                }
                ptsOut[i] = (float)Vc * 1.1;
            }
            return ptsOut;
        }
        //******************************************************
        private PointF[] Energy2Array(Energy enrg, bool pileup)
        {
            int w = pBx1.Width;
            PointF[] ptsIn = new PointF[pBx1.Width];
            int pw = rnd.Next(5,10);
            if (pileup)
            {//Pileup
                int x1 = 0;
                int xd = w * pw / 100;
                int y1 = 0;
                int y2 = (int)((bmp.Height * 0.8) * enrg.en[enrg.plsPtr]);
                int y3 = (int)((bmp.Height * 0.8) * enrg.en[1 - enrg.plsPtr]);
                int xt = (int)((bmp.Width) * enrg.tm);
                for (int i = 0; i < x1; i++)
                {
                    ptsIn[i].X = i;
                    ptsIn[i].Y = y1;
                }
                for (int i = x1; i < x1 +xd; i++)
                {
                    ptsIn[i].X = i;
                    ptsIn[i].Y = y2;
                }
                for (int i = x1 + xd; i < x1 + xd + xt; i++)
                {
                    ptsIn[i].X = i;
                    ptsIn[i].Y = y1;
                }
                for (int i = x1 + xd + xt; i < x1 + xd + xt + xd; i++)
                {
                    ptsIn[i].X = i;
                    ptsIn[i].Y = y3;
                }
                for (int i = x1 + xd + xt + xd; i < pBx1.Width; i++)
                {
                    ptsIn[i].X = i;
                    ptsIn[i].Y = y1;
                }
            }
            else
            {//Normal
                int x1 = 0;
                int xd = w * pw / 100;
                int y1 = 0;
                int y2 = (int)((bmp.Height * 0.8) * enrg.en[enrg.plsPtr]);
                for (int i = 0; i < x1; i++)
                {
                    ptsIn[i].X = i;
                    ptsIn[i].Y = y1;
                }
                for (int i = x1; i < x1 + xd; i++)
                {
                    ptsIn[i].X = i;
                    ptsIn[i].Y = y2;
                }
                for (int i = x1 + xd ; i < pBx1.Width; i++)
                {
                    ptsIn[i].X = i;
                    ptsIn[i].Y = y1;
                }
            }
            return ptsIn;
        }
        //******************************************************
        private void timer1_Tick(object sender, EventArgs e)
        {
            Pen pn = new Pen(Color.Blue);
            double[] pulseDt = new double[500];
            int tx = 2 + rnd.Next(10);//pulse start point;
            int tw1 = 15;//pulse width;
            //double vy = rnd.NextDouble() * 0.9 + 0.1;
            double vy = Get8ChnlGaussianPulses();
            for (int i = tx; i < tx + tw1; i++)
            {
                pulseDt[i] = vy;
            }

            if (rnd.Next(pileUpPro) == 0)
            {
                pileUpFlg = true;
                int tw2 = rnd.Next(2, 10);//gap between pulses in pile up;
                vy = rnd.NextDouble() * 0.9 + 0.1;
                for (int i = tx + tw1 + tw2; i < tx + tw1 + tw2 + tw1; i++)
                {
                    pulseDt[i] = vy;
                }
                pn = new Pen(Color.Red);
                //return;
            }
            else
            {
                pileUpFlg = false;
                pn = new Pen(Color.Yellow);
            }
            pulseDt = Array2ShapeDbl(pulseDt);
            pulseDt = Array2ShapeDbl(pulseDt);
            pulseDt = Array2ShapeDbl(pulseDt);
            PointF[] ptsF = new PointF[pulseDt.Length];
            int x1 = 0;//start sampling at x1
            bool flg = true;
            double yMx = double.MinValue;
            int xMx = 0;
            for (int i = 0; i < pulseDt.Length; i++)
            {
                ptsF[i].X = i;
                ptsF[i].Y = (float)(bmp.Height * pulseDt[i]);
                if (ptsF[i].Y >= bmp.Height)
                {
                }
                if (flg == true)
                {
                    if (pulseDt[i] >= 100.0 / 4096.0)
                    {//if pulse height is more then 100th channel in 4096 channel analyser
                        x1 = i;
                        flg = false;
                    }
                }
                if (yMx < pulseDt[i])
                {
                    yMx = pulseDt[i];
                    xMx = i;
                }
            }
            int sw = 15;//sample width

            //bmp = new Bitmap(pBx1.Width / 3, pBx1.Height);
            bmp.RotateFlip(RotateFlipType.RotateNoneFlipY);
            g = Graphics.FromImage(bmp);
            //g.Clear(Color.Black);
            g.DrawLines(pn, ptsF);
            //g.DrawLine(Pens.Blue, x1, 0, x1, (int)(bmp.Height * pulseDt[x1]));
            //g.DrawLine(Pens.Blue, x1 + sw * 1, 0, x1 + sw * 1, (int)(bmp.Height * pulseDt[x1 + sw * 1]));
            //g.DrawLine(Pens.Blue, x1 + sw * 2, 0, x1 + sw * 2, (int)(bmp.Height * pulseDt[x1 + sw * 2]));
            //g.DrawLine(Pens.Blue, x1 + sw * 3, 0, x1 + sw * 3, (int)(bmp.Height * pulseDt[x1 + sw * 3]));
            g.Dispose();
            bmp.RotateFlip(RotateFlipType.RotateNoneFlipY);
            pBx1.Image = bmp;
            int[] ptsPtrs=new int[5];
            ptsPtrs[0] = xMx;
            ptsPtrs[1] = x1 + sw * 0;
            ptsPtrs[2] = x1 + sw * 1;
            ptsPtrs[3] = x1 + sw * 2;
            ptsPtrs[4] = x1 + sw * 3;
            if (SavePulseDataChkBx.Checked == true)
                SavePulse2File(svflnm, pileUpFlg, ptsPtrs, pulseDt);
        }
        //******************************************************
        private double Get8ChnlGaussianPulses()
        {
            int chnSel = rnd.Next(chnlinfo.Length);
            int hgtSel = rnd.Next(chnlinfo[chnSel].profile.Length);
            int hgtVal = chnlinfo[chnSel].height + chnlinfo[chnSel].profile[hgtSel];
            double ht = hgtVal / 4096.0;
            //double retVal = ht * ((chnlinfo[chnSel].span) + chnlinfo[chnSel].profile[hgtSel]) / (chnlinfo[chnSel].span);
            //if (retVal > 0.7)
            //{
            //}
            return ht;
        }
        //******************************************************
        private void LoadDataBtn_Click(object sender, EventArgs e)
        {
            openFileDialog1.InitialDirectory = dirPath;
            openFileDialog1.Filter = "Text (*.txt;)|*.txt|" + "All files (*.*)|*.*";
            openFileDialog1.Multiselect = true;
            openFileDialog1.Title = "Select Pulse Data Files - Pileup";
            if (DialogResult.Cancel == openFileDialog1.ShowDialog()) return;
            flnmLst = openFileDialog1.FileNames;
            pulsedata2 = new PulseData2[flnmLst.Length][];
            for (int i = 0; i < flnmLst.Length; i++)
            {
              string[] lines = File.ReadAllLines(flnmLst[i]);
              pulsedata2[i] = new PulseData2[lines.Length];
              for (int j = 0; j < lines.Length; j++)
              {
                  string[] wrds = lines[j].Split(':');
                  string[] ptrs = wrds[0].Split(',');
                  string[] smpls = wrds[1].Split(',');
                  pulsedata2[i][j].isPileup = int.Parse(ptrs[0]);

                  pulsedata2[i][j].pts = new PointF[smpls.Length];
                  for (int k = 0; k < smpls.Length; k++)
                  {
                      pulsedata2[i][j].pts[k].X = k;
                      pulsedata2[i][j].pts[k].Y = (float)(double.Parse(smpls[k]) *bmp.Height);
                  }
                  pulsedata2[i][j].pos = new int[ptrs.Length - 1];
                  pulsedata2[i][j].nnIn = new double[ptrs.Length - 2];
                  for (int k = 1; k < ptrs.Length; k++)
                  {
                      pulsedata2[i][j].pos[k-1] = int.Parse(ptrs[k]);
                  }
                  for (int k = 1; k < pulsedata2[i][j].pos.Length; k++)
                  {
                      pulsedata2[i][j].nnIn[k - 1] = ((int)(double.Parse(smpls[pulsedata2[i][j].pos[k]])*4096))/4096.0;
                      //double tmp1 = double.Parse(smpls[pulsedata2[i][j].pos[k]]);
                      //double tmp2 = pulsedata2[i][j].nnIn[k - 1];
                  }
                  int npk = int.Parse(ptrs[1]);
                  pulsedata2[i][j].peak.X = npk;
                  pulsedata2[i][j].peak.Y = (float)(double.Parse(smpls[npk]));
              }
            }
        }
        //******************************************************
        private void LoadFile2PulseData(string ldflnm, ArrayList ldPulseData)
        {
            ldPulseData = new ArrayList();
            PulseData2 pd;
            string[] lines = File.ReadAllLines(ldflnm);
            for (int i = 0; i < lines.Length; i++)
            {
                string[] wrds = lines[i].Split(',');
                pd = new PulseData2();
                if (System.Convert.ToInt16(wrds[0]) == 1)
                    pd.isPileup = 1;
                else if (System.Convert.ToInt16(wrds[0]) == 0)
                    pd.isPileup = 0;
                pd.pts = new PointF[wrds.Length - 1];
                for (int j = 1; j < wrds.Length; j++)
                {
                    string[] wrds1 = wrds[j].Split(',');
                    pd.pts[j - 1] = new PointF(float.Parse(wrds1[0]), float.Parse(wrds1[1]));
                }
                ldPulseData.Add(pd);
            }
        }
        //******************************************************
        private void ConfgBtn_Click(object sender, EventArgs e)
        {
            try
            {
                Process.Start(cfgFlnm);
            }
            catch
            {
                string dt = "Items, Height, Count, Width\nMaxVals, 4096,1000,32";
                File.WriteAllText(cfgFlnm, dt);
            }
        }
        //******************************************************
        private void btnTestScan_Click(object sender, EventArgs e)
        {
            if (btnTestScan.Text == "Scan Start")
            {
                btnTestScan.Text = "Scan Stop";
                scanCount = 0;
                chnErr=new int[4096];
                timer3.Interval = 1;
                timer3.Start();
            }
            else
            {
                btnTestScan.Text = "Scan Start";
                timer3.Stop();
                lblTest.Text = chnErr[0].ToString() + ":" + chnErr[1].ToString() + ":" + chnErr[2].ToString() + ":" + chnErr[3].ToString();
            }
        }
        //******************************************************
        private void timer3_Tick(object sender, EventArgs e)
        {
            btnTestWave_Click(null, null);
            scanCount++;
        }
        //******************************************************
        private void PulsePlotPeakTest(int i, int j, double[] yk)
        {
            bmp = new Bitmap(pBx1.Width / 3, pBx1.Height);

            int npk = pulsedata2[i][j].pos[0];
            int nmn = pulsedata2[i][j].pos[1];
            int nmx = pulsedata2[i][j].pos[pulsedata2[i][j].pos.Length - 1];
            //nnbp.yk[0] = (double)(nmx - npk) / (nmx - nmn);
            int npk2 = (int)(nmx - nnbp.yk[0] * (nmx - nmn));
            int xmx = (int)(npk2);
            float ymx = (float)(nnbp.yk[1] * bmp.Height);

            //int xmx = (int)((yk[0] * (xMax - xMin) + xMin));
            //float ymx = (float)(yk[1] * bmp.Height);

            int x1 = (int)(pulsedata2[i][j].pos[1]);
            float y1 = (float)(pulsedata2[i][j].nnIn[0] * bmp.Height);
            int x2 = (int)(pulsedata2[i][j].pos[2]);
            float y2 = (float)(pulsedata2[i][j].nnIn[1] * bmp.Height);
            int x3 = (int)(pulsedata2[i][j].pos[3]);
            float y3 = (float)(pulsedata2[i][j].nnIn[2] * bmp.Height);
            int x4 = (int)(pulsedata2[i][j].pos[4]);
            float y4 = (float)(pulsedata2[i][j].nnIn[3] * bmp.Height);
            //bmp = new Bitmap(pBx1.Width, pBx1.Height);
            g = Graphics.FromImage(bmp);
            g.Clear(Color.Black);
            g.DrawLine(Pens.Blue, x1, y1, x1, 0);
            g.DrawLine(Pens.Blue, x2, y2, x2, 0);
            g.DrawLine(Pens.Blue, x3, y3, x3, 0);
            g.DrawLine(Pens.Blue, x4, y4, x4, 0);
            g.DrawLine(Pens.Red, xmx, ymx, xmx, 0);

            //g.DrawLine(Pens.Green, xmx, ymx, xmx, 10);

            g.DrawLines(Pens.Yellow, pulsedata2[i][j].pts);
            g.Dispose();
            bmp.RotateFlip(RotateFlipType.RotateNoneFlipY);
            pBx1.Image = bmp;
        }
        //******************************************************
        private void btnTest2Csv_Click(object sender, EventArgs e)
        {
            //......................................................
            //if (btnTest2Csv.Text == "Test2CsvON")
            //{
                saveFileDialog1.InitialDirectory = dirPath;
                saveFileDialog1.Filter = "CSV (*.csv;)|*.csv|" + "All files (*.*)|*.*";
                saveFileDialog1.Title = "Save Test CSV File";
                if (DialogResult.Cancel == saveFileDialog1.ShowDialog()) return;
                testCsvFlnm = saveFileDialog1.FileName;
                string[] words = testCsvFlnm.Split(new Char[] { '.' });
                string s1 = words[words.Length - 1];
                //if (s1 != "csv")
                    //testCsvFlnm = testCsvFlnm + ".csv";
                
                //btnTest2Csv.Text = "Test2CsvOFF";
                scanCount = 0;
                chnErr = new int[4096];
                test2CsvStr = "";
                lblTest.BackColor = Color.LightSalmon;
                lblTest.Text = "Wait...!!!";
                this.Refresh();
                bool noiseFlg = false;
                int pileupCnt = 0;
                if (DialogResult.Yes == MessageBox.Show("Include Noise?", "Choose", MessageBoxButtons.YesNo))
                {
                    noiseFlg = true;
                }
                int zeroCnt=0;
                StreamWriter sw = new StreamWriter("HeightFor4096.csv");
                //......................................................
                if (RadbtnPeak.Checked)
                {
                    //double error = 0;
                    for (int i = 0; i < pulsedata2.Length; i++)
                    {
                        int temp1 = 0;
                        for (int j = 0; j < pulsedata2[i].Length; j++)
                        {
                            scanCount++;
                            if (pulsedata2[i][j].isPileup == 1)
                            {
                                pileupCnt++;
                                continue;
                            }
                            for (int k = 0; k < pulsedata2[i][j].nnIn.Length; k++)
                            {
                                nnbp.yi[k] = pulsedata2[i][j].nnIn[k];
                                if (noiseFlg)
                                {
                                    double temp = rnd.NextDouble() - 0.5;
                                    nnbp.yi[k] += (temp) / 4096.0;
                                    if (temp == 0)
                                        zeroCnt++;
                                }
                            }
                            int npk = pulsedata2[i][j].pos[0];
                            int nmn = pulsedata2[i][j].pos[1];
                            int nmx = pulsedata2[i][j].pos[pulsedata2[i][j].pos.Length - 1];
                            nnbp.outk[0] = (double)(nmx - npk) / (nmx - nmn);
                            nnbp.outk[1] = pulsedata2[i][j].peak.Y;
                            double[] err = nnbp.UpdateNetErrors();//in %
                            int errN = (int)(err[1] * 4096);
                            chnErr[errN]++;
                            lblTest.Text = errN.ToString() + " Chn";
                            //PulsePlotPeakTest(i, j, nnbp.yk);
                            string flnmTemp = Path.GetFileName(flnmLst[i]);
                            test2CsvStr += flnmTemp + "," + j.ToString() + "," + errN.ToString() + "," + pulsedata2[i][j].isPileup.ToString() + "\n";
                            temp1 = j;
                            string s = Math.Round((nnbp.outk[1] * 1.8), 5) + "," + Math.Round((nnbp.yk[1] * 1.8), 5);
                            sw.WriteLine(s);
                        }
                        PulsePlotPeakTest(i, temp1, nnbp.yk);
                    }
                    sw.Close();
                    //test2CsvStr += scanCount.ToString();
                    lblTest.BackColor = Color.Transparent; 
                    lblTest.Text = chnErr[0].ToString() 
                        + ":" + chnErr[1].ToString() 
                        + ":" + chnErr[2].ToString() 
                        + ":" + chnErr[3].ToString();
                    string str;
                    string result = "\n";
                    int chnErrSum = 0;
                    for (int i = 0; i < chnErr.Length; i++)
                    {
                        if (chnErr[i] != 0)
                            result += i.ToString() + " Chnl:" + chnErr[i].ToString() + "\n";
                        chnErrSum += chnErr[i];
                        if (chnErrSum == scanCount)
                            break;
                    }
                    str = "Result: " + result +
                        "Total Pulses: " + scanCount.ToString() + "\n" +
                        "Pileup Pulses(NA): " + pileupCnt.ToString() + "\n" +
                        "Normal Pulses: " + (scanCount - pileupCnt) + "\n" +
                        "Zero Noise Count: " + zeroCnt + "\n";
                    MessageBox.Show(str);
                }
                //......................................................
                if (RadbtnPileup.Checked)
                {
                    double error = 0;
                    double errorTotal = 0;
                    for (int i = 0; i < pulsedata2.Length; i++)
                    {
                        int temp2 = 0;
                        for (int j = 0; j < pulsedata2[i].Length; j++)
                        {
                            for (int k = 0; k < pulsedata2[i][j].nnIn.Length; k++)
                            {
                                nnbp.yi[k] = pulsedata2[i][j].nnIn[k];
                            }
                            if (pulsedata2[i][j].isPileup == 0)
                            {
                                nnbp.outk[0] = 0;
                                nnbp.outk[1] = 1;
                            }
                            else
                            {
                                nnbp.outk[0] = 1;
                                nnbp.outk[1] = 0;
                            }
                            error = nnbp.UpdateNet();
                            error = Math.Round(error, 3);
                            errorTotal += error;
                            lblTest.Text = error.ToString();
                            //PulsePlotTest(i, j, nnbp.yk);
                            string flnmTemp = Path.GetFileName(flnmLst[i]);
                            //test2CsvStr += flnmTemp + "," + j.ToString() + "," + error.ToString() + "," + pulsedata2[i][j].isPileup.ToString() + "\n";
                            scanCount++;
                            temp2 = j;
                        }
                        PulsePlotTest(i, temp2, nnbp.yk);
                    }
                    //test2CsvStr += scanCount.ToString();
                    errorTotal /= scanCount;
                    lblTest.BackColor = Color.Transparent;
                    lblTest.Text = scanCount.ToString() + ":" + Math.Round(errorTotal, 3).ToString() + Math.Round(errorTotal * scanCount,3).ToString();
                }
                //......................................................
            //}
            //......................................................
            //else if (btnTest2Csv.Text == "Test2CsvOFF")
            //{
            //    btnTest2Csv.Text = "Test2CsvON";
            //    saveFileDialog1.InitialDirectory = dirPath;
            //    saveFileDialog1.Filter = "CSV (*.csv;)|*.csv|" + "All files (*.*)|*.*";
            //    saveFileDialog1.Title = "Save Test CSV File";
            //    if (DialogResult.Cancel == saveFileDialog1.ShowDialog()) return;
            //    testCsvFlnm = saveFileDialog1.FileName;
            //    string[] words = testCsvFlnm.Split(new Char[] { '.' });
            //    string s1 = words[words.Length - 1];
            //    //if (s1 != "csv")
            //        //testCsvFlnm = testCsvFlnm + ".csv";
            //    File.WriteAllText(testCsvFlnm, test2CsvStr);
            //}
            //lblTest.BackColor = Color.Transparent;
            //lblTest.Text = chnErr[0].ToString() + ":" + chnErr[1].ToString() + ":" + chnErr[2].ToString() + ":" + chnErr[3].ToString();
            File.WriteAllText(testCsvFlnm, test2CsvStr);
        }
        //******************************************************
        private void btnTest2CsvNew_Click(object sender, EventArgs e)
        {
            saveFileDialog1.InitialDirectory = dirPath;
            saveFileDialog1.Filter = "CSV (*.csv;)|*.csv|" + "All files (*.*)|*.*";
            saveFileDialog1.Title = "Save Test CSV File";
            if (DialogResult.Cancel == saveFileDialog1.ShowDialog()) return;
            testCsvFlnm = saveFileDialog1.FileName;
            string[] words = testCsvFlnm.Split(new Char[] { '.' });
            string s1 = words[words.Length - 1];
            scanCount = 0;
            chnErr = new int[4096];
            test2CsvStr = "";
            lblTest.BackColor = Color.LightSalmon;
            lblTest.Text = "Wait...!!!";
            this.Refresh();
            bool noiseFlg = false;
            int pileupCnt = 0;
            int zeroNoiseCnt = 0;
            if (DialogResult.Yes == MessageBox.Show("Include Noise?", "Choose", MessageBoxButtons.YesNo))
            {
                noiseFlg = true;
            }
            //......................................................
            if (RadbtnPeak.Checked)
            {
                for (int i = 0; i < pulsedata2.Length; i++)
                {
                    int temp1 = 0;
                    for (int j = 0; j < pulsedata2[i].Length; j++)
                    {
                        scanCount++;
                        if (pulsedata2[i][j].isPileup == 1)
                        {
                            //continue;
                            pileupCnt++;
                        }
                        for (int k = 0; k < pulsedata2[i][j].nnIn.Length; k++)
                        {
                            nnbp.yi[k] = pulsedata2[i][j].nnIn[k];
                            if (noiseFlg)
                            {
                                double temp = rnd.NextDouble() - 0.5;
                                nnbp.yi[k] += (temp) / 4096.0;
                                if (temp == 0)
                                    zeroNoiseCnt++;
                            }
                        }
                        int npk = pulsedata2[i][j].pos[0];
                        int nmn = pulsedata2[i][j].pos[1];
                        int nmx = pulsedata2[i][j].pos[pulsedata2[i][j].pos.Length - 1];
                        nnbp.outk[0] = (double)(nmx - npk) / (nmx - nmn);
                        nnbp.outk[1] = pulsedata2[i][j].peak.Y;
                        double[] err = nnbp.UpdateNetErrors();//in %
                        int errN = (int)(err[1] * 4096);
                        chnErr[errN]++;
                        lblTest.Text = errN.ToString() + " Chn";
                        string flnmTemp = Path.GetFileName(flnmLst[i]);
                        test2CsvStr += flnmTemp + "," + j.ToString() + "," + errN.ToString() + "," + pulsedata2[i][j].isPileup.ToString() + "\n";
                        temp1 = j;
                        //if (pulsedata2[i][j].isPileup == 1 && (errN == 0 || errN == 1))
                        //    MessageBox.Show(flnmTemp + "," + j.ToString() + "," + errN.ToString() + "," + pulsedata2[i][j].isPileup.ToString() + "\n");
                    }
                    PulsePlotPeakTest(i, temp1, nnbp.yk);
                }
                lblTest.BackColor = Color.Transparent;
                lblTest.Text = chnErr[0].ToString()
                    + ":" + chnErr[1].ToString()
                    + ":" + chnErr[2].ToString()
                    + ":" + chnErr[3].ToString()
                    + ":" + chnErr[4].ToString()
                    + ":" + chnErr[5].ToString();
                File.WriteAllText(testCsvFlnm, test2CsvStr);
                string str;
                string result="\n";
                int chnErrSum = 0;
                for (int i = 0; i < chnErr.Length; i++)
                {
                    if (chnErr[i] != 0)
                        result += i.ToString().PadLeft(5) + " Chnl:  " + chnErr[i].ToString().PadLeft(7) + "\t";
                    if (i >= 15 && i % 15 == 0)
                        result += "\n";
                    chnErrSum += chnErr[i];
                    if (chnErrSum == scanCount)
                        break;
                }
                result = "\n" + "Chn 0" + ": " + chnErr[0].ToString() + "\n" +
                    "Chn 1" + ": " + chnErr[1].ToString() + "\n" +
                    "Chn 2" + ": " + chnErr[2].ToString() + "\n" +
                    "Chn 3" + ": " + chnErr[3].ToString() + "\n" +
                    "Chn 4" + ": " + chnErr[4].ToString() + "\n" +
                    "Chn 5" + ": " + chnErr[5].ToString() + "\n" +
                    "Chn 6" + ": " + chnErr[6].ToString() + "\n" +
                    "Chn 7" + ": " + chnErr[7].ToString() + "\n" +
                    "Chn 8" + ": " + chnErr[8].ToString() + "\n" +
                    "Chn 9" + ": " + chnErr[9].ToString() + "\n" +
                    "Chn 10" + ": " + chnErr[10].ToString() + "\n" +
                    "Chn 11" + ": " + chnErr[11].ToString() + "\n" +
                    "Chn 12" + ": " + chnErr[12].ToString() + "\n" +
                    "Chn 13" + ": " + chnErr[13].ToString() + "\n" +
                    "Chn 14" + ": " + chnErr[14].ToString() + "\n" +
                    "Chn 15" + ": " + chnErr[15].ToString() + "\n" +
                    "Chn 16" + ": " + chnErr[16].ToString() + "\n" +
                    "Chn 17" + ": " + chnErr[17].ToString() + "\n" +
                    "Chn 18" + ": " + chnErr[18].ToString() + "\n";
                str = "Result: " + result +
                    "Total Pulses: " + scanCount.ToString() + "\n" +
                    "Pileup Pulses: " + pileupCnt.ToString() + "\n" +
                    "Normal Pulses: " + (scanCount - pileupCnt) + "\n" +
                    "Zero Noise Count: " + zeroNoiseCnt + "\n";

                MessageBox.Show(str);
            }
        }
        //******************************************************
    }
}