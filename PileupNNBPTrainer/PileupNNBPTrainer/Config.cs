using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.Text;
using System.Windows.Forms;

namespace PileupNNBPTrainer
{
    public struct PileupConfig
    {
        public double[] energy;
        public int[] count;
        public double[] noise;
    }
    public partial class Config : Form
    {
        //*******************************************************************
        //Global Variables
        public PileupConfig pileupconfig;
        public PileupNNBPTrainer pileupNNBPtrainer;
        //*******************************************************************
        public Config()
        {
            InitializeComponent();
        }
        //*******************************************************************
        private void Config_Shown(object sender, EventArgs e)
        {
            //pileupconfig = new PileupConfig();
        }
        //*******************************************************************
        private void richTextBox1_MouseUp(object sender, MouseEventArgs e)
        {
            if (e.Button == MouseButtons.Right)
            {
                string[] lines = richTextBox1.Lines;
            }
        }
        //*******************************************************************
        private void Config_FormClosing(object sender, FormClosingEventArgs e)
        {
            if (pileupNNBPtrainer.IsDisposed == false)
            {
                this.Hide();
                e.Cancel = true;
                return;
            }
        }
        //*******************************************************************
    }
}