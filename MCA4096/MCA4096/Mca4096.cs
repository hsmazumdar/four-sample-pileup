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

namespace MCA4096
{
    public partial class Mca4096 : Form
    {
        //***********************************************************
        struct ChannelInfo
        {
            public string name;
            public int height;
            public int count;
            public int span;
            public short[] profile;
        }
        enum MnuItm { New = 0, Position, Height, Width };

        UInt32 rndIn = 0x55555555;
        ChannelInfo[] chnlinfo;
        UInt32[] mcaBuf;
        Bitmap bmp;
        Bitmap bmpMouse;
        Bitmap bmpProfile, bmpProfileSel;
        DateTime dtSt;
        DateTime dtEn;
        //UInt32 rnd32;
        string cfgFlnm = "config.csv";
        int channels = 4096;
        int count = 1000;
        int span = 1000;
        int chMx = 8;
        Point mouseDn;
        Point mouseMov;
        Graphics grmou;
        ContextMenu cm;
        ArrayList chnLst;
        int ii = 0;
        double wt = 1;
        double pos = 1;
        double ht = 1;
        double[][] htData;
        int htDataCounter = 0;
        int htDataMx = 0;
        //***********************************************************
        public Mca4096()
        {
            InitializeComponent();
            //cfgData = Properties.Resources.config.Replace("\r\n", "\n").TrimEnd('\n');
            cfgFlnm = Application.StartupPath + @"\config.csv";
            bmpProfile = Properties.Resources.Profile;
            bmpProfileSel = Properties.Resources.ProfileSel;
            this.MouseWheel += new MouseEventHandler(this.pictureBox1_MouseWheel);
        }
        //***********************************************************
        private void ExitBtn_Click(object sender, EventArgs e)
        {
            this.Close();
        }
        //***********************************************************
        private void StartStopBtn_Click(object sender, EventArgs e)
        {
            //rnd32 = (UInt32)0x80200003;

            if (StartStopBtn.Text == "Start")
            {
                //LoadParameters(cfgFlnm);
                //tst = new ushort[channels];
//                mcaBuf = new UInt32[channels];//clear MCA buffer
                StartStopBtn.Text = "Stop";
                //dtSt = DateTime.Now;
                timer1.Interval = 10;
                htDataCounter = 0;
                timer1.Start();
            }
            else
            {
                StartStopBtn.Text = "Start";
                timer1.Stop();
            }
        }
        //***********************************************************
        private void timer1_Tick(object sender, EventArgs e)
        {
            if (chkBxImport.Checked)
            {
                if (chMx == 0 || htDataCounter == htDataMx)
                {
                    StartStopBtn.Text = "Start";
                    timer1.Stop();
                    return;
                }
                int chn2 = (int)(htData[htDataCounter][0] * 4095);
                mcaBuf[chn2]++;
                htDataCounter++;
                Plot();
                dtEn = DateTime.Now;
                long tm = (dtEn.Ticks - dtSt.Ticks) / 10000;
                float t1 = tm / 1000.0f;
                label2.Text = t1.ToString();
            }
            else
            {
                if (chMx == 0)
                {
                    StartStopBtn.Text = "Start";
                    timer1.Stop();
                    return;
                }
                for (int s = 0; s < 1000; s++)
                {
                    int chn = (int)Random32((UInt32)chMx);
                    int spr = (int)Random32((UInt32)count);
                    if (chnlinfo[chn].count >= spr)
                    {
                        int no = (int)Random32((UInt32)chnlinfo[chn].profile.Length);
                        int chn2 = chnlinfo[chn].profile[no] + chnlinfo[chn].height;
                        mcaBuf[chn2]++;
                    }
                }
                Plot();
                dtEn = DateTime.Now;
                long tm = (dtEn.Ticks - dtSt.Ticks) / 10000;
                float t1 = tm / 1000.0f;
                label2.Text = t1.ToString();
            }
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
        //***********************************************************
        private void InitDisplay()
        {
            bmp = new Bitmap(channels, 512);
            Graphics g = Graphics.FromImage(bmp);
            g.Clear(Color.Black);
            for (int x = 0; x < bmp.Width; x += 25)
            {
                if (x % 250 == 0)
                {
                    g.DrawLine(Pens.White, new Point(x - 1, 511), new Point(x - 1, 500));
                    g.DrawLine(Pens.White, new Point(x, 511), new Point(x, 500));
                    g.DrawLine(Pens.White, new Point(x + 1, 511), new Point(x + 1, 500));
                }
                else
                {
                    g.DrawLine(Pens.White, new Point(x, 511), new Point(x, 500));
                }
            }
            for (int x = 0; x < bmp.Width; x += 250)
            {
                g.DrawLine(Pens.Green, new Point(x, 0), new Point(x, 500));
            }
            for (int y = 0; y < bmp.Height; y += 125)
            {
                g.DrawLine(Pens.Green, new Point(0, y), new Point(bmp.Width - 1, y));
            }
            g.Dispose();
            pictureBox1.Image = bmp;
        }
        //***********************************************************
        private void Plot()
        {
            bmp = new Bitmap(channels, 512);
            Graphics g = Graphics.FromImage(bmp);
            g.Clear(Color.Black);
            for (int x = 0; x < bmp.Width; x+=25)
            {
                if (x % 250 == 0)
                {
                    g.DrawLine(Pens.White, new Point(x - 1, 511), new Point(x - 1, 500));
                    g.DrawLine(Pens.White, new Point(x, 511), new Point(x, 500));
                    g.DrawLine(Pens.White, new Point(x + 1, 511), new Point(x + 1, 500));
                }
                else
                {
                    g.DrawLine(Pens.White, new Point(x, 511), new Point(x, 500));
                }
            }
            for (int x = 0; x < bmp.Width; x += 250)
            {
                g.DrawLine(Pens.Green, new Point(x, 0), new Point(x, 500));
            }
            for (int y = 0; y < bmp.Height; y += 125)
            {
                g.DrawLine(Pens.Green, new Point(0, y), new Point(bmp.Width-1, y));
            }
            UInt32 mxVal = UInt32.MinValue;
            for (int n = 0; n < channels; n++)
            {
                mxVal = Math.Max(mcaBuf[n], mxVal);
            }
            UInt32 scal = 1 + mxVal / 500;
            for (int n = 0; n < channels; n++)
            {
                if (mcaBuf[n] > 0)
                {
                    g.DrawLine(Pens.Yellow, new Point(n, 500), new Point(n, 500 - (int)(mcaBuf[n] / scal)));
                }
            }
            g.Dispose();
            pictureBox1.Image = bmp;
        }
        //***********************************************************
        private UInt32 Random32(UInt32 range)
        {
            UInt32 d1 = rndIn;
            UInt32 d2 = (d1 & 0x00000001);
            d1 = d1 >> 1;
            d2 ^= (d1 & 0x00000001);
            d1 = d1 >> 20;
            d2 ^= (d1 & 0x00000001);
            d1 = d1 >> 10;
            d2 ^= (d1 & 0x00000001);
            rndIn = rndIn << 1;
            rndIn += d2;
            return rndIn % range;
        }
        //***********************************************************
        private void Mca4096_Shown(object sender, EventArgs e)
        {
            InitDisplay();
            //LoadParameters(cfgFlnm);
            //mcaBuf = new UInt32[channels];//clear MCA buffer
            //dtSt = DateTime.Now;
            DefaultBtn_Click(null, null);
            Plot();
//            MenuItem posEvnt=new MenuItem();
            cm = new ContextMenu();
            cm.MenuItems.Add("New", AddNewChannel_Click);
            cm.MenuItems.Add("Position", AdjustPosition_Click);
            cm.MenuItems.Add("Height", AdjustHeight_Click);
            cm.MenuItems.Add("Width", AdjustWidth_Click);
            cm.MenuItems[0].Checked = true;
            //pictureBox1.ContextMenu = cm;
            chnLst = new ArrayList();
        }
        //***********************************************************
        private void AddNewChannel_Click(object sender, EventArgs e)
        {
            for (int i = 0; i < cm.MenuItems.Count; i++)
            {
                cm.MenuItems[i].Checked = false;
            }
            MenuItem mi = (MenuItem)sender;
            mi.Checked ^= true;
            label3.Text = "New";
        }
        //***********************************************************
        private void AdjustPosition_Click(object sender, EventArgs e)
        {
            chnLst.Sort();
            for (int i = 0; i < cm.MenuItems.Count; i++)
            {
                cm.MenuItems[i].Checked = false;
            }
            MenuItem mi = (MenuItem)sender;
            mi.Checked ^= true;
            label3.Text = "Position";
        }
        //***********************************************************
        private void AdjustHeight_Click(object sender, EventArgs e)
        {
            chnLst.Sort();
            for (int i = 0; i < cm.MenuItems.Count; i++)
            {
                cm.MenuItems[i].Checked = false;
            }
            MenuItem mi = (MenuItem)sender;
            mi.Checked ^= true;
            label3.Text = "Height";
        }
        //***********************************************************
        private void AdjustWidth_Click(object sender, EventArgs e)
        {
            chnLst.Sort();
            for (int i = 0; i < cm.MenuItems.Count; i++)
            {
                cm.MenuItems[i].Checked = false;
            }
            MenuItem mi = (MenuItem)sender;
            mi.Checked ^= true;
            label3.Text = "Width";
        }
        //***********************************************************
        private void Mca4096_ResizeEnd(object sender, EventArgs e)
        {
            InitDisplay();
            Plot();
        }
        //***********************************************************
        private void ConfigBtn_Click(object sender, EventArgs e)
        {
            Process.Start(cfgFlnm);
        }
        //***********************************************************
        private void TestBtn_Click(object sender, EventArgs e)
        {
        }
        //***********************************************************
        private void ResetBtn_Click(object sender, EventArgs e)
        {
            //LoadParameters(cfgFlnm);
            //mcaBuf = new UInt32[channels];//clear MCA buffer
            //dtSt = DateTime.Now;
            ResetCurrentConfig();
            Plot();
        }
        //***********************************************************
        private void SaveBtn_Click(object sender, EventArgs e)
        {
            //Items	    Height	Count	Width
            //MaxVals	4096	1000	32
            //Channel1	100	    300	    50
            //Channel2	500	    222	    70
            saveFileDialog1.Filter = "Text File (.txt)|*.txt|All File (All)|*.*";
            saveFileDialog1.InitialDirectory = Application.StartupPath + @"\Data";
            if (Directory.Exists(saveFileDialog1.InitialDirectory) == false)
                Directory.CreateDirectory(saveFileDialog1.InitialDirectory);
            if (saveFileDialog1.ShowDialog() == DialogResult.Cancel)
                return;
            string flnm = saveFileDialog1.FileName;
            if (File.Exists(flnm) == false)
            {

            }
            StreamWriter sw = new StreamWriter(flnm);
            sw.WriteLine("Items, Height, Count, Width");
            sw.WriteLine("MaxVals, " + channels.ToString() + "," + count.ToString() + "," + span.ToString());
            for (int i = 0; i < chnlinfo.Length; i++)
            {
                sw.WriteLine(chnlinfo[i].name + "," + chnlinfo[i].height.ToString() + "," + chnlinfo[i].count.ToString() + "," + chnlinfo[i].span.ToString());
            }
            sw.WriteLine("#MCA-Buffer");
            string str = "";
            for (int i = 0; i < mcaBuf.Length; i++)
            {
                str += mcaBuf[i].ToString() + ",";
            }
            str = str.TrimEnd(',');
            sw.WriteLine(str);
            sw.Close();
        }
        //***********************************************************
        private void LoadBtn_Click(object sender, EventArgs e)
        {
            openFileDialog1.InitialDirectory = Application.StartupPath + @"\Data";
            openFileDialog1.Filter = "Text File (.txt)|*.txt|All File (All)|*.*";
            openFileDialog1.Multiselect = false;
            if (openFileDialog1.ShowDialog() == DialogResult.Cancel)
                return;
            string flnm = openFileDialog1.FileName;
            LoadParametersFromTextFile(flnm);
            Plot();
        }
        //***********************************************************
        private void LoadParametersFromTextFile(string cfgFlnm)
        {
            //f{x)=a*exp(-(x-b)^2/(2*c^2))
            string[] lines = File.ReadAllLines(cfgFlnm);
            channels = System.Convert.ToInt16(lines[1].Split(',')[1]);
            count = System.Convert.ToInt16(lines[1].Split(',')[2]);
            span = System.Convert.ToInt16(lines[1].Split(',')[3]);
            chMx = lines.Length - 4;
            chnlinfo = new ChannelInfo[chMx];
            for (int i = 0; i < chMx; i++)
            {
                string[] wrds = lines[i + 2].Split(',');
                chnlinfo[i].name = wrds[0];
                chnlinfo[i].height = System.Convert.ToInt16(wrds[1]);
                chnlinfo[i].count = System.Convert.ToInt16(wrds[2]);
                chnlinfo[i].span = System.Convert.ToInt16(wrds[3]);
            }
            FillChannelConfig();
            string[] wrds1 = lines[lines.Length - 1].Split(',');
            mcaBuf = new UInt32[channels];
            for (int i = 0; i < wrds1.Length; i++)
            {
                mcaBuf[i] = System.Convert.ToUInt32(wrds1[i]);
            }
            // WriteCurrentConfig();
           // ResetBtn_Click(null, null);
        }
        //***********************************************************
        private void FillChannelConfig()
        {
            double[] yy = new double[channels];
            for (int i = 0; i < channels; i++)
            {
                yy[i] = Math.Exp(-(i - channels / 2.0) * (i - channels / 2.0) / (channels * channels * 0.05));
            }
            for (int i = 0; i < chMx; i++)
            {
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
        //***********************************************************
        private void WriteCurrentConfig()
        {
            StreamWriter sw = new StreamWriter(cfgFlnm);
            sw.WriteLine("Items, Height, Count, Width");
            sw.WriteLine("MaxVals, " + channels.ToString() + "," + count.ToString() + "," + span.ToString());
            for (int i = 0; i < chnlinfo.Length; i++)
            {
                sw.WriteLine(chnlinfo[i].name + "," + chnlinfo[i].height.ToString() + "," + chnlinfo[i].count.ToString() + "," + chnlinfo[i].span.ToString());
            }
            sw.Close();
        }
        //***********************************************************
        private void ClearCurrentConfig()
        {
            chMx = 0;
            chnlinfo = new ChannelInfo[chMx];
            mcaBuf = new UInt32[channels];//clear MCA buffer
            dtSt = DateTime.Now;
        }
        //***********************************************************
        private void ResetCurrentConfig()
        {
            mcaBuf = new UInt32[channels];//clear MCA buffer
            dtSt = DateTime.Now;
        }
        //***********************************************************
        private void PlotConfig()
        {
            bmpMouse = (Bitmap)bmp.Clone();
            grmou = Graphics.FromImage(bmpMouse);
            for (int i = 0; i < chnLst.Count; i++)
            {
                int xx = (int)chnLst[i];
                if (ii == i)
                {
                    int mouseMovX = xx - (int)(bmpProfileSel.Width * wt) / 2;
                    //grmou.DrawImage(bmpProfileSel, mouseMovX, bmpMouse.Height - bmpProfileSel.Height - 12, new Rectangle(0, 0, bmpProfileSel.Width, bmpProfileSel.Height), GraphicsUnit.Pixel);
                    grmou.DrawImage(bmpProfileSel, new Rectangle(mouseMovX , bmpMouse.Height - (int)(bmpProfileSel.Height * ht) - 12, (int)(bmpProfileSel.Width*wt), (int)(bmpProfileSel.Height * ht)), 
                        new Rectangle(0, 0, bmpProfileSel.Width, bmpProfileSel.Height), GraphicsUnit.Pixel);
                }
                else
                {
                    int mouseMovX = xx - bmpProfileSel.Width / 2;
                    grmou.DrawImage(bmpProfile, mouseMovX, bmpMouse.Height - bmpProfile.Height - 12, new Rectangle(0, 0, bmpProfile.Width, bmpProfile.Height), GraphicsUnit.Pixel);
                }

            }
            pictureBox1.Image = bmpMouse;
        }
        //***********************************************************
        private void pictureBox1_MouseWheel(object sender, MouseEventArgs e)
        {
            if (ConfigChkBx.Checked)
            {
                if (cm.MenuItems[(int)MnuItm.New].Checked == true)
                {//New
                }
                if (cm.MenuItems[(int)MnuItm.Position].Checked == true)
                {//Position

                }
                if (cm.MenuItems[(int)MnuItm.Height].Checked == true)
                {//Height
                    if (e.Delta > 0)
                        ht *= 1.01;
                    else
                        ht /= 1.01;
                    PlotConfig();
                }
                if (cm.MenuItems[(int)MnuItm.Width].Checked == true)
                {//Width
                    if (e.Delta > 0)
                        wt *= 1.01;
                    else
                        wt /= 1.01;
                    PlotConfig();
                }
            }
        }
        //***********************************************************
        private void pictureBox1_MouseDown(object sender, MouseEventArgs e)
        {
            if (e.Button == MouseButtons.Left)
            {
                mouseDn = mouseMov = new Point(e.X * bmp.Width / pictureBox1.Width, e.Y * bmp.Height / pictureBox1.Height);
                if (ConfigChkBx.Checked)
                {
                    if (cm.MenuItems[(int)MnuItm.New].Checked == true)
                    {
                        if (bmpMouse != null)
                        {
                            bmpMouse.Dispose();
                        }
                        bmpMouse = (Bitmap)bmp.Clone();
                        grmou = Graphics.FromImage(bmpMouse);
                        //chnLst.Add(mouseMov.X + bmpProfile.Width / 2);
                        mouseMov = new Point(e.X * bmp.Width / pictureBox1.Width - bmpProfile.Width / 2, e.Y * bmp.Height / pictureBox1.Height);
                        grmou.DrawImage(bmpProfile, mouseMov.X, bmpMouse.Height - bmpProfile.Height - 12, new Rectangle(0, 0, bmpProfile.Width, bmpProfile.Height), GraphicsUnit.Pixel);
                        pictureBox1.Image = bmpMouse;
                        timer2.Interval = 300;
                        timer2.Start();
                    }
                    if (cm.MenuItems[(int)MnuItm.Position].Checked == true)
                    {
                        int xxMn = int.MaxValue;
                        ii = 0;
                        for (int i = 0; i < chnLst.Count; i++)
                        {
                            int xx = Math.Abs((int)chnLst[i]-mouseMov.X);
                            if (xxMn > xx)
                            {
                                xxMn = xx;
                                ii = i;
                            }
                        }
                        label3.Text = ii.ToString();
                        PlotConfig();
                    }
                }
                else
                {
                }
            }
        }
        //***********************************************************
        private void pictureBox1_MouseMove(object sender, MouseEventArgs e)
        {
            if (e.Button == MouseButtons.Left)
            {
                if (ConfigChkBx.Checked)
                {
                    if (cm.MenuItems[(int)MnuItm.New].Checked == true)
                    {
                        grmou.FillRectangle(Brushes.Black, new Rectangle(mouseMov.X, bmpMouse.Height - bmpProfile.Height - 12, bmpProfile.Width, bmpProfile.Height));
                        mouseMov = new Point(e.X * bmp.Width / pictureBox1.Width - bmpProfile.Width / 2, e.Y * bmp.Height / pictureBox1.Height);
                        grmou.DrawImage(bmpProfile, mouseMov.X, bmpMouse.Height - bmpProfile.Height - 12, new Rectangle(0, 0, bmpProfile.Width, bmpProfile.Height), GraphicsUnit.Pixel);
                        pictureBox1.Image = bmpMouse;
                        timer2.Interval = 300;
                        timer2.Start();
                    }
                }
                else
                {
                }
            }
        }
        //***********************************************************
        private void pictureBox1_MouseUp(object sender, MouseEventArgs e)
        {
            if (e.Button == MouseButtons.Right)
            {
                if (ConfigChkBx.Checked)
                {
                    cm.Show(pictureBox1,new Point(e.X,e.Y));
                }
            }
            if (e.Button == MouseButtons.Left)
            {
                if (ConfigChkBx.Checked)
                {
                    if (cm.MenuItems[(int)MnuItm.New].Checked == true)
                    {
                        Graphics g = Graphics.FromImage(bmp);
                        mouseMov = new Point(e.X * bmp.Width / pictureBox1.Width - bmpProfile.Width / 2, e.Y * bmp.Height / pictureBox1.Height);
                        g.DrawImage(bmpProfile, mouseMov.X, bmpMouse.Height - bmpProfile.Height - 12, new Rectangle(0, 0, bmpProfile.Width, bmpProfile.Height), GraphicsUnit.Pixel);
                        g.Dispose();
                        pictureBox1.Image = bmp;
                        bmpMouse.Dispose();
                        grmou.Dispose();
                        chnLst.Add(mouseMov.X + bmpProfile.Width / 2);
                    }
                }
                else 
                {
                    //chMx = chnLst.Count;
                    //chnlinfo = new ChannelInfo[chMx];
                    //for (int i = 0; i < chnlinfo.Length; i++)
                    //{
                    //    int no = i + 1;
                    //    chnlinfo[i].name = "Chnl-" + "," + no.ToString();
                    //    chnlinfo[i].height = (int)chnLst[i];
                    //    chnlinfo[i].span = 100;
                    //    chnlinfo[i].count = 500;
                    //}
                    //FillChannelConfig();
                }
            }
        }
        //***********************************************************
        private void ConfigChkBx_CheckedChanged(object sender, EventArgs e)
        {
            if (ConfigChkBx.Checked)
            {
                //StreamWriter sw = new StreamWriter(cfgFlnm);
                //sw.WriteLine("Items, Height, Count, Width");
                //sw.WriteLine("MaxVals, " + channels.ToString() + "," + count.ToString() + "," + span.ToString());
                //sw.Close();
                //LoadParameters(cfgFlnm);
                //mcaBuf = new UInt32[channels];//clear MCA buffer
                //dtSt = DateTime.Now;
                ClearCurrentConfig();
                chnLst = new ArrayList();
                Plot();
            }
            else 
            {

                chMx = chnLst.Count;
                chnlinfo = new ChannelInfo[chMx];
                for (int i = 0; i < chnlinfo.Length; i++)
                {
                    int no = i + 1;
                    chnlinfo[i].name = "Chnl-" + "," + no.ToString();
                    chnlinfo[i].height = (int)chnLst[i];
                    chnlinfo[i].span = 100;
                    chnlinfo[i].count = 500;
                }
                FillChannelConfig();
            }
        }
        //***********************************************************
        private void timer2_Tick(object sender, EventArgs e)
        {
            int xx = mouseMov.X + bmpProfile.Width / 2;
            //int yy = mouseMov.Y + bmpProfile.Height / 2;
            if (xx < 0) xx = 0;
            if (xx >= channels) xx = channels - 1;
            label3.Text = "ChNo:" + xx.ToString();
            timer2.Stop();
        }
        //***********************************************************
        private void DefaultBtn_Click(object sender, EventArgs e)
        {
            LoadParameters(cfgFlnm);
            mcaBuf = new UInt32[channels];//clear MCA buffer
            dtSt = DateTime.Now;
        }

        private void chkBxImport_CheckedChanged(object sender, EventArgs e)
        {
            if (chkBxImport.Checked)
            {
                string[] wrds = File.ReadAllLines("HeightFor4096.csv");
                htData = new double[wrds.Length][];
                htDataMx = wrds.Length;
                for (int i = 0; i < wrds.Length; i++)
                {
                    string[] wrds1 = wrds[i].Split(',');
                    htData[i] = new double[2];
                    htData[i][0] = double.Parse(wrds1[0]);
                    htData[i][1] = double.Parse(wrds1[1]);
                }
            }
            else
            {
            }
        }
        //***********************************************************
    }
}