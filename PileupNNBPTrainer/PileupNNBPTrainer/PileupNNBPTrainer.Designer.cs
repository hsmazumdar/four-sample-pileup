namespace PileupNNBPTrainer
{
    partial class PileupNNBPTrainer
    {
        /// <summary>
        /// Required designer variable.
        /// </summary>
        private System.ComponentModel.IContainer components = null;

        /// <summary>
        /// Clean up any resources being used.
        /// </summary>
        /// <param name="disposing">true if managed resources should be disposed; otherwise, false.</param>
        protected override void Dispose(bool disposing)
        {
            if (disposing && (components != null))
            {
                components.Dispose();
            }
            base.Dispose(disposing);
        }

        #region Windows Form Designer generated code

        /// <summary>
        /// Required method for Designer support - do not modify
        /// the contents of this method with the code editor.
        /// </summary>
        private void InitializeComponent()
        {
            this.components = new System.ComponentModel.Container();
            this.btnExit = new System.Windows.Forms.Button();
            this.btnTestWave = new System.Windows.Forms.Button();
            this.btnNewNet = new System.Windows.Forms.Button();
            this.btnTngStart = new System.Windows.Forms.Button();
            this.btnSaveNet = new System.Windows.Forms.Button();
            this.btnLoadNet = new System.Windows.Forms.Button();
            this.timer1 = new System.Windows.Forms.Timer(this.components);
            this.openFileDialog1 = new System.Windows.Forms.OpenFileDialog();
            this.saveFileDialog1 = new System.Windows.Forms.SaveFileDialog();
            this.panel1 = new System.Windows.Forms.Panel();
            this.btnTest2Csv = new System.Windows.Forms.Button();
            this.RadbtnPileup = new System.Windows.Forms.RadioButton();
            this.RadbtnPeak = new System.Windows.Forms.RadioButton();
            this.btnTestScan = new System.Windows.Forms.Button();
            this.ConfgBtn = new System.Windows.Forms.Button();
            this.LoadDataBtn = new System.Windows.Forms.Button();
            this.SavePulseDataChkBx = new System.Windows.Forms.CheckBox();
            this.PulseBtn = new System.Windows.Forms.Button();
            this.lblTest = new System.Windows.Forms.Label();
            this.pBx1 = new System.Windows.Forms.PictureBox();
            this.timer2 = new System.Windows.Forms.Timer(this.components);
            this.timer3 = new System.Windows.Forms.Timer(this.components);
            this.btnTest2CsvNew = new System.Windows.Forms.Button();
            this.panel1.SuspendLayout();
            ((System.ComponentModel.ISupportInitialize)(this.pBx1)).BeginInit();
            this.SuspendLayout();
            // 
            // btnExit
            // 
            this.btnExit.Anchor = ((System.Windows.Forms.AnchorStyles)((System.Windows.Forms.AnchorStyles.Bottom | System.Windows.Forms.AnchorStyles.Right)));
            this.btnExit.Location = new System.Drawing.Point(509, 479);
            this.btnExit.Name = "btnExit";
            this.btnExit.Size = new System.Drawing.Size(87, 23);
            this.btnExit.TabIndex = 0;
            this.btnExit.Text = "Exit";
            this.btnExit.UseVisualStyleBackColor = true;
            this.btnExit.Click += new System.EventHandler(this.btnExit_Click);
            // 
            // btnTestWave
            // 
            this.btnTestWave.Anchor = ((System.Windows.Forms.AnchorStyles)((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Right)));
            this.btnTestWave.Location = new System.Drawing.Point(509, 186);
            this.btnTestWave.Name = "btnTestWave";
            this.btnTestWave.Size = new System.Drawing.Size(87, 23);
            this.btnTestWave.TabIndex = 22;
            this.btnTestWave.Text = "Test";
            this.btnTestWave.UseVisualStyleBackColor = true;
            this.btnTestWave.Click += new System.EventHandler(this.btnTestWave_Click);
            // 
            // btnNewNet
            // 
            this.btnNewNet.Anchor = ((System.Windows.Forms.AnchorStyles)((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Right)));
            this.btnNewNet.Location = new System.Drawing.Point(509, 69);
            this.btnNewNet.Name = "btnNewNet";
            this.btnNewNet.Size = new System.Drawing.Size(87, 23);
            this.btnNewNet.TabIndex = 21;
            this.btnNewNet.Text = "New Net";
            this.btnNewNet.UseVisualStyleBackColor = true;
            this.btnNewNet.Click += new System.EventHandler(this.btnNewNet_Click);
            // 
            // btnTngStart
            // 
            this.btnTngStart.Anchor = ((System.Windows.Forms.AnchorStyles)((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Right)));
            this.btnTngStart.Location = new System.Drawing.Point(509, 157);
            this.btnTngStart.Name = "btnTngStart";
            this.btnTngStart.Size = new System.Drawing.Size(87, 23);
            this.btnTngStart.TabIndex = 19;
            this.btnTngStart.Text = "Tng Start";
            this.btnTngStart.UseVisualStyleBackColor = true;
            this.btnTngStart.Click += new System.EventHandler(this.btnTngStart_Click);
            // 
            // btnSaveNet
            // 
            this.btnSaveNet.Anchor = ((System.Windows.Forms.AnchorStyles)((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Right)));
            this.btnSaveNet.Location = new System.Drawing.Point(509, 128);
            this.btnSaveNet.Name = "btnSaveNet";
            this.btnSaveNet.Size = new System.Drawing.Size(87, 23);
            this.btnSaveNet.TabIndex = 18;
            this.btnSaveNet.Text = "Save Net";
            this.btnSaveNet.UseVisualStyleBackColor = true;
            this.btnSaveNet.Click += new System.EventHandler(this.btnSaveNet_Click);
            // 
            // btnLoadNet
            // 
            this.btnLoadNet.Anchor = ((System.Windows.Forms.AnchorStyles)((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Right)));
            this.btnLoadNet.Location = new System.Drawing.Point(509, 99);
            this.btnLoadNet.Name = "btnLoadNet";
            this.btnLoadNet.Size = new System.Drawing.Size(87, 23);
            this.btnLoadNet.TabIndex = 17;
            this.btnLoadNet.Text = "Load Net";
            this.btnLoadNet.UseVisualStyleBackColor = true;
            this.btnLoadNet.Click += new System.EventHandler(this.btnLoadNet_Click);
            // 
            // timer1
            // 
            this.timer1.Tick += new System.EventHandler(this.timer1_Tick);
            // 
            // openFileDialog1
            // 
            this.openFileDialog1.FileName = "openFileDialog1";
            // 
            // panel1
            // 
            this.panel1.Anchor = ((System.Windows.Forms.AnchorStyles)((((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Bottom)
                        | System.Windows.Forms.AnchorStyles.Left)
                        | System.Windows.Forms.AnchorStyles.Right)));
            this.panel1.Controls.Add(this.btnTest2CsvNew);
            this.panel1.Controls.Add(this.btnTest2Csv);
            this.panel1.Controls.Add(this.RadbtnPileup);
            this.panel1.Controls.Add(this.RadbtnPeak);
            this.panel1.Controls.Add(this.btnTestScan);
            this.panel1.Controls.Add(this.ConfgBtn);
            this.panel1.Controls.Add(this.LoadDataBtn);
            this.panel1.Controls.Add(this.SavePulseDataChkBx);
            this.panel1.Controls.Add(this.PulseBtn);
            this.panel1.Controls.Add(this.lblTest);
            this.panel1.Controls.Add(this.pBx1);
            this.panel1.Controls.Add(this.btnTestWave);
            this.panel1.Controls.Add(this.btnLoadNet);
            this.panel1.Controls.Add(this.btnNewNet);
            this.panel1.Controls.Add(this.btnExit);
            this.panel1.Controls.Add(this.btnSaveNet);
            this.panel1.Controls.Add(this.btnTngStart);
            this.panel1.Location = new System.Drawing.Point(0, 0);
            this.panel1.Name = "panel1";
            this.panel1.Size = new System.Drawing.Size(603, 508);
            this.panel1.TabIndex = 23;
            // 
            // btnTest2Csv
            // 
            this.btnTest2Csv.Anchor = ((System.Windows.Forms.AnchorStyles)((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Right)));
            this.btnTest2Csv.Location = new System.Drawing.Point(510, 244);
            this.btnTest2Csv.Name = "btnTest2Csv";
            this.btnTest2Csv.Size = new System.Drawing.Size(87, 23);
            this.btnTest2Csv.TabIndex = 33;
            this.btnTest2Csv.Text = "Test2Csv";
            this.btnTest2Csv.UseVisualStyleBackColor = true;
            this.btnTest2Csv.Click += new System.EventHandler(this.btnTest2Csv_Click);
            // 
            // RadbtnPileup
            // 
            this.RadbtnPileup.Anchor = ((System.Windows.Forms.AnchorStyles)((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Right)));
            this.RadbtnPileup.AutoSize = true;
            this.RadbtnPileup.Location = new System.Drawing.Point(509, 325);
            this.RadbtnPileup.Name = "RadbtnPileup";
            this.RadbtnPileup.Size = new System.Drawing.Size(54, 17);
            this.RadbtnPileup.TabIndex = 32;
            this.RadbtnPileup.TabStop = true;
            this.RadbtnPileup.Text = "Pileup";
            this.RadbtnPileup.UseVisualStyleBackColor = true;
            // 
            // RadbtnPeak
            // 
            this.RadbtnPeak.Anchor = ((System.Windows.Forms.AnchorStyles)((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Right)));
            this.RadbtnPeak.AutoSize = true;
            this.RadbtnPeak.Checked = true;
            this.RadbtnPeak.Location = new System.Drawing.Point(509, 302);
            this.RadbtnPeak.Name = "RadbtnPeak";
            this.RadbtnPeak.Size = new System.Drawing.Size(50, 17);
            this.RadbtnPeak.TabIndex = 31;
            this.RadbtnPeak.TabStop = true;
            this.RadbtnPeak.Text = "Peak";
            this.RadbtnPeak.UseVisualStyleBackColor = true;
            // 
            // btnTestScan
            // 
            this.btnTestScan.Anchor = ((System.Windows.Forms.AnchorStyles)((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Right)));
            this.btnTestScan.Location = new System.Drawing.Point(509, 215);
            this.btnTestScan.Name = "btnTestScan";
            this.btnTestScan.Size = new System.Drawing.Size(87, 23);
            this.btnTestScan.TabIndex = 29;
            this.btnTestScan.Text = "Scan Start";
            this.btnTestScan.UseVisualStyleBackColor = true;
            this.btnTestScan.Click += new System.EventHandler(this.btnTestScan_Click);
            // 
            // ConfgBtn
            // 
            this.ConfgBtn.Anchor = ((System.Windows.Forms.AnchorStyles)((System.Windows.Forms.AnchorStyles.Bottom | System.Windows.Forms.AnchorStyles.Right)));
            this.ConfgBtn.Location = new System.Drawing.Point(509, 415);
            this.ConfgBtn.Name = "ConfgBtn";
            this.ConfgBtn.Size = new System.Drawing.Size(87, 23);
            this.ConfgBtn.TabIndex = 28;
            this.ConfgBtn.Text = "ConfigOn";
            this.ConfgBtn.UseVisualStyleBackColor = true;
            this.ConfgBtn.Click += new System.EventHandler(this.ConfgBtn_Click);
            // 
            // LoadDataBtn
            // 
            this.LoadDataBtn.Anchor = ((System.Windows.Forms.AnchorStyles)((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Right)));
            this.LoadDataBtn.Location = new System.Drawing.Point(509, 40);
            this.LoadDataBtn.Name = "LoadDataBtn";
            this.LoadDataBtn.Size = new System.Drawing.Size(87, 23);
            this.LoadDataBtn.TabIndex = 27;
            this.LoadDataBtn.Text = "Load Data";
            this.LoadDataBtn.UseVisualStyleBackColor = true;
            this.LoadDataBtn.Click += new System.EventHandler(this.LoadDataBtn_Click);
            // 
            // SavePulseDataChkBx
            // 
            this.SavePulseDataChkBx.Anchor = ((System.Windows.Forms.AnchorStyles)((System.Windows.Forms.AnchorStyles.Bottom | System.Windows.Forms.AnchorStyles.Right)));
            this.SavePulseDataChkBx.AutoSize = true;
            this.SavePulseDataChkBx.Location = new System.Drawing.Point(509, 444);
            this.SavePulseDataChkBx.Name = "SavePulseDataChkBx";
            this.SavePulseDataChkBx.Size = new System.Drawing.Size(67, 17);
            this.SavePulseDataChkBx.TabIndex = 26;
            this.SavePulseDataChkBx.Text = "SaveFile";
            this.SavePulseDataChkBx.UseVisualStyleBackColor = true;
            // 
            // PulseBtn
            // 
            this.PulseBtn.Anchor = ((System.Windows.Forms.AnchorStyles)((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Right)));
            this.PulseBtn.Location = new System.Drawing.Point(509, 12);
            this.PulseBtn.Name = "PulseBtn";
            this.PulseBtn.Size = new System.Drawing.Size(87, 23);
            this.PulseBtn.TabIndex = 25;
            this.PulseBtn.Text = "SimStart";
            this.PulseBtn.UseVisualStyleBackColor = true;
            this.PulseBtn.Click += new System.EventHandler(this.PulseBtn_Click);
            // 
            // lblTest
            // 
            this.lblTest.Anchor = ((System.Windows.Forms.AnchorStyles)((System.Windows.Forms.AnchorStyles.Bottom | System.Windows.Forms.AnchorStyles.Right)));
            this.lblTest.AutoSize = true;
            this.lblTest.Location = new System.Drawing.Point(509, 464);
            this.lblTest.Name = "lblTest";
            this.lblTest.Size = new System.Drawing.Size(13, 13);
            this.lblTest.TabIndex = 24;
            this.lblTest.Text = "--";
            // 
            // pBx1
            // 
            this.pBx1.Anchor = ((System.Windows.Forms.AnchorStyles)((((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Bottom)
                        | System.Windows.Forms.AnchorStyles.Left)
                        | System.Windows.Forms.AnchorStyles.Right)));
            this.pBx1.BorderStyle = System.Windows.Forms.BorderStyle.FixedSingle;
            this.pBx1.Location = new System.Drawing.Point(3, 3);
            this.pBx1.Name = "pBx1";
            this.pBx1.Size = new System.Drawing.Size(500, 500);
            this.pBx1.SizeMode = System.Windows.Forms.PictureBoxSizeMode.StretchImage;
            this.pBx1.TabIndex = 23;
            this.pBx1.TabStop = false;
            // 
            // timer2
            // 
            this.timer2.Tick += new System.EventHandler(this.timer2_Tick);
            // 
            // timer3
            // 
            this.timer3.Tick += new System.EventHandler(this.timer3_Tick);
            // 
            // btnTest2CsvNew
            // 
            this.btnTest2CsvNew.Anchor = ((System.Windows.Forms.AnchorStyles)((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Right)));
            this.btnTest2CsvNew.Location = new System.Drawing.Point(509, 273);
            this.btnTest2CsvNew.Name = "btnTest2CsvNew";
            this.btnTest2CsvNew.Size = new System.Drawing.Size(87, 23);
            this.btnTest2CsvNew.TabIndex = 34;
            this.btnTest2CsvNew.Text = "TestPeak";
            this.btnTest2CsvNew.UseVisualStyleBackColor = true;
            this.btnTest2CsvNew.Click += new System.EventHandler(this.btnTest2CsvNew_Click);
            // 
            // PileupNNBPTrainer
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(6F, 13F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.ClientSize = new System.Drawing.Size(608, 514);
            this.Controls.Add(this.panel1);
            this.Name = "PileupNNBPTrainer";
            this.Text = "Pileup Neural Network Trainer - R&D, DDU";
            this.Shown += new System.EventHandler(this.PileupNNBPTrainer_Shown);
            this.panel1.ResumeLayout(false);
            this.panel1.PerformLayout();
            ((System.ComponentModel.ISupportInitialize)(this.pBx1)).EndInit();
            this.ResumeLayout(false);

        }

        #endregion

        private System.Windows.Forms.Button btnExit;
        private System.Windows.Forms.Button btnTestWave;
        private System.Windows.Forms.Button btnNewNet;
        private System.Windows.Forms.Button btnTngStart;
        private System.Windows.Forms.Button btnSaveNet;
        private System.Windows.Forms.Button btnLoadNet;
        private System.Windows.Forms.Timer timer1;
        private System.Windows.Forms.OpenFileDialog openFileDialog1;
        private System.Windows.Forms.SaveFileDialog saveFileDialog1;
        private System.Windows.Forms.Panel panel1;
        private System.Windows.Forms.PictureBox pBx1;
        private System.Windows.Forms.Label lblTest;
        private System.Windows.Forms.Button PulseBtn;
        private System.Windows.Forms.Timer timer2;
        private System.Windows.Forms.CheckBox SavePulseDataChkBx;
        private System.Windows.Forms.Button LoadDataBtn;
        private System.Windows.Forms.Button ConfgBtn;
        private System.Windows.Forms.Button btnTestScan;
        private System.Windows.Forms.Timer timer3;
        private System.Windows.Forms.RadioButton RadbtnPileup;
        private System.Windows.Forms.RadioButton RadbtnPeak;
        private System.Windows.Forms.Button btnTest2Csv;
        private System.Windows.Forms.Button btnTest2CsvNew;
    }
}

