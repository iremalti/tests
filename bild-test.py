import os
import numpy as np
import torch.nn as nn
import torch.backends.cudnn as cudnn
import torch.optim as optim
import torch.utils.data
import torchvision.datasets as dset
import torchvision.transforms as transforms
import torchvision.utils as vutils
import cv2
from pytorch_grad_cam import GradCAM
from pytorch_grad_cam.utils.model_targets import ClassifierOutputTarget
from typing import  List
from pytorch_grad_cam.activations_and_gradients import ActivationsAndGradients
from pytorch_grad_cam.utils.image import show_cam_on_image, \
    preprocess_image
from PIL import Image
import requests


CUDA = True
DATA_PATH = 'C:\\Users\\altipair\\Desktop\\Data\\Bilder'
OUT_PATH = 'C:\\Users\\altipair\\Desktop\\bachelor\\ausgabe'
output_folder = 'C:\\Users\\altipair\\Desktop\\bachelor\\CAM'
LOG_FILE = os.path.join(OUT_PATH, 'log.txt')
BATCH_SIZE = 128
IMAGE_CHANNEL = 3
Z_DIM = 100
G_HIDDEN = 64
X_DIM = 64
D_HIDDEN = 64
EPOCH_NUM = 2
REAL_LABEL = 1.
FAKE_LABEL = 0.
lr = 2e-4
seed = 1

# utils.clear_folder(OUT_PATH)
print("Logging to {}\n".format(LOG_FILE))
#sys.stdout = utils.StdOut(LOG_FILE)
CUDA = CUDA and torch.cuda.is_available()
print("Cuda is available = ", torch.cuda.is_available())

print("Pytorch version: {} ".format(torch.__version__))
if CUDA:
    print("CUDA version: {}\n".format(torch.version.cuda))
if seed is None:
    seed = np.random.randint(1, 10000)
print("Random Seed: ", seed)
np.random.seed(seed)
torch.manual_seed(seed)
if CUDA:
    torch.cuda.manual_seed(seed)
cudnn.benchmark =True
device = torch.device("cuda:0" if CUDA else "cpu")


#Generator

class Generator (nn.Module):
    def __init__(self):
        super(Generator, self).__init__()       #selbst implementierter generator  kommt in die klasse nn.Modul
        self.main = nn.Sequential(
            nn.ConvTranspose2d(Z_DIM, G_HIDDEN * 8 , 4, 1, 0, bias = False),
            nn.BatchNorm2d(G_HIDDEN * 8),
            nn.ReLU(True),
            nn.ConvTranspose2d(G_HIDDEN * 8, G_HIDDEN * 4, 4, 2, 1, bias = False),
            nn.BatchNorm2d(G_HIDDEN *4),
            nn.ReLU(True),
            nn.ConvTranspose2d(G_HIDDEN * 4,G_HIDDEN * 2, 4, 2, 1, bias = False),
            nn.BatchNorm2d(G_HIDDEN * 2),
            nn.ReLU(True),
            nn.ConvTranspose2d(G_HIDDEN * 2, G_HIDDEN, 4, 2, 1, bias = False),
            nn.BatchNorm2d(G_HIDDEN),
            nn.ReLU(True),
            nn.ConvTranspose2d(G_HIDDEN, IMAGE_CHANNEL, 4, 2, 1, bias = False),
            nn.Tanh()
        )
    def forward(self, input):
        return self.main(input)

def weights_init(m):
    classname = m.__class__.__name__
    if classname.find('Conv') != -1:
        m.weight.data.normal_(0.0, 0.02)
    elif classname.find('BatchNorm') != -1:
        m.weight.data.normal_(1.0, 0.02)
        m.bias.data.fill_(0)

#Diskriminator

class Diskriminator(nn.Module):
    def __init__(self):
        super(Diskriminator, self).__init__()
        self.main = nn.Sequential(
            nn.Conv2d(IMAGE_CHANNEL, D_HIDDEN, 4, 2, 1, bias = False),
            nn.LeakyReLU(0.2, inplace = True),
            nn.Conv2d(D_HIDDEN, D_HIDDEN * 2, 4, 2, 1, bias = False),
            nn.BatchNorm2d(D_HIDDEN * 2),
            nn.LeakyReLU(0.2, inplace = True),
            nn.Conv2d(D_HIDDEN * 2, D_HIDDEN * 4, 4, 2, 1, bias = False),
            nn.BatchNorm2d(D_HIDDEN * 4),
            nn.LeakyReLU(0.2, inplace = True),
            nn.Conv2d(D_HIDDEN * 4, D_HIDDEN * 8, 4, 2, 1, bias = False),
            nn.BatchNorm2d(D_HIDDEN * 8),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Conv2d(D_HIDDEN * 8, 1, 4, 1, 0, bias = False),
            nn.Sigmoid()
        )
       # self.classifier = self.main.classifier
        self.gradient = None

    def activations_hook(self, grad):
        self.gradients = grad

    def get_activations_gradient(self):
        return self.gradients

    def get_activations(self, x):
        return self.main[-2]

    def forward(self, x):
       # h = x.register_hook(self.activations_hook)
        x = self.main(x).view(-1, 1).squeeze(1)
        return x


if __name__ == '__main__':

    netG = Generator().to(device)
    netG.apply(weights_init)
    print(netG)

    netD = Diskriminator().to(device)
    netD.apply(weights_init)
    print(netD)

    print(netD.main[-2])

    criterion = nn.BCELoss()

    optimizerD = optim.Adam(netD.parameters(), lr = lr, betas = (0.5, 0.999))
    optimizerG = optim.Adam(netG.parameters(), lr = lr, betas = (0.5, 0.999))

    dataset = dset.ImageFolder(root = DATA_PATH,
                             transform = transforms.Compose([
                                 transforms.Resize(X_DIM),
                                 transforms.CenterCrop(X_DIM),
                                 transforms.ToTensor(),
                                 transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))
                                 ]))


    assert dataset
    dataloader = torch.utils.data.DataLoader(dataset, batch_size = BATCH_SIZE, shuffle = True, num_workers = 4)

    viz_noise = torch.randn(BATCH_SIZE, Z_DIM, 1, 1, device = device)
    for epoch in range (EPOCH_NUM):
        for i, data in enumerate(dataloader):
            x_real = data[0].to(device)
            real_label = torch.full((x_real.size(0),), REAL_LABEL, device = device)
            fake_label = torch.full((x_real.size(0),), FAKE_LABEL, device = device)

            netD.zero_grad()
            y_real = netD(x_real)
            loss_D_real = criterion(y_real, real_label)
            loss_D_real.backward()

            z_noise = torch.randn(x_real.size(0), Z_DIM, 1, 1, device = device)
            x_fake = netG(z_noise)
            y_fake = netD(x_fake.detach())
            loss_D_fake = criterion(y_fake, fake_label)
            loss_D_fake.backward()
            optimizerD.step()

            netG.zero_grad()
            y_fake_r = netD(x_fake)
            loss_G = criterion(y_fake_r, real_label)
            loss_G. backward()
            optimizerG.step()

            if i % 100 == 0:
                print('Epoche {}[{}/{}] loss_D_real: {:.4f} loss_D_fake: {:.4f} loss_G: {:.4f}'.format(epoch, i, len(dataloader),
                                                                                                loss_D_real.mean().item(),
                                                                                                loss_D_fake.mean().item(),
                                                                                                loss_G.mean().item(), ))

            if i % 100 == 0:
                ...
                vutils.save_image(x_real, os.path.join(OUT_PATH, 'real_sample_bild.png'), normalize = True)
                with torch.no_grad():
                    viz_sample = netG(viz_noise)
                    vutils.save_image(viz_sample, os.path.join(OUT_PATH, 'fake_sample_bild_{}.png'.format(epoch)),normalize=True)
                    torch.save(netG.state_dict(), os.path.join(OUT_PATH, 'netG_{}.pth'.format(epoch)))
                    torch.save(netD.state_dict(), os.path.join(OUT_PATH, 'netD_{}.pth'.format(epoch)))

                netD = netD.cpu()
                model = netD
                target_layers = netD.main[-1]
                print(target_layers)

             #   img, _ = next(iter(dataloader))
                img = cv2.imread('C:\\Users\\altipair\\Desktop\\bachelor\\ausgabe\\fake_sample_bild_{}.png'.format(epoch), 1)[:, :,::-1]

            #    img = np.array(Image.open(requests.get(image, stream=True).raw))
            #    img = cv2.resize(img, (224, 224))
                img = np.float32(img) / 255

                input_tensor = preprocess_image(img, mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])

            #    pred = netD(img).argmax(dim=1)
            #    pred[386, :].backward()

                targets = None

                with GradCAM(model=model, target_layers=target_layers, use_cuda= True) as cam:
                    cam.batch_size = 32
                    grayscale_cam = cam(input_tensor=input_tensor,targets=targets,aug_smooth=False,eigen_smooth=False)
                    grayscale_cam = grayscale_cam[0, :]
                    cam_image = show_cam_on_image(img, grayscale_cam, use_rgb=True)
                    cam_image = cv2.cvtColor(cam_image, cv2.COLOR_RGB2BGR)

                    output_tensor = netD(input_tensor)
                    last_layer_output = output_tensor[:, -2]  # Ausgabe der vorletzten Schicht extrahieren