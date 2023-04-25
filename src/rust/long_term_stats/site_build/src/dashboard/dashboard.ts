import html from './template.html';
import { Page } from '../page'
import { MenuPage } from '../menu/menu';
import { Component } from '../components/component';
import { NodeStatus } from '../components/node_status';
import { PacketsChart } from '../components/packets';
import { ThroughputChart } from '../components/throughput';

export class DashboardPage implements Page {
    menu: MenuPage;
    components: Component[]

    constructor() {
        this.menu = new MenuPage("menuDash");
        let container = document.getElementById('mainContent');
        if (container) {
            container.innerHTML = html;
        }
        this.components = [
            new NodeStatus(),
            new PacketsChart(),
            new ThroughputChart(),
        ];
    }

    wireup() {
        this.components.forEach(component => {
            component.wireup();
        });
    }    

    ontick(): void {
        this.menu.ontick();
        this.components.forEach(component => {
            component.ontick();
        });
    }

    onmessage(event: any) {
        if (event.msg) {
            this.menu.onmessage(event);

            this.components.forEach(component => {
                component.onmessage(event);
            });            
        }
    }
}